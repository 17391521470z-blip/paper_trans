from __future__ import annotations

import base64
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.order import Order, OrderStatus, PaymentMethod
from app.models.quota import Quota, QuotaTier
from app.schemas.order import CreateOrderRequest

settings = get_settings()
logger = get_logger(__name__)

router: APIRouter = APIRouter()

TIER_CONFIG: dict[QuotaTier, dict[str, int]] = {
    QuotaTier.STANDARD: {"monthly_pages": 200, "daily_pages": 50},
    QuotaTier.PRO: {"monthly_pages": 1000, "daily_pages": 200},
}


@router.post(
    "",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="创建订单（微信/支付宝）",
)
async def create_order(payload: CreateOrderRequest) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "detail": "Not implemented yet",
            "endpoint": "/api/v1/orders",
            "received": {
                "tier": payload.tier,
                "payment_method": payload.payment_method,
                "quantity": payload.quantity,
            },
        },
    )


@router.get(
    "",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="列出当前用户的订单",
)
async def list_orders() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "detail": "Not implemented yet",
            "endpoint": "/api/v1/orders",
        },
    )


def verify_wechat_sign(params: dict[str, str], sign: str, api_key: str) -> bool:
    try:
        sorted_keys = sorted(k for k in params if k != "sign")
        sign_str = "&".join(f"{k}={params[k]}" for k in sorted_keys) + f"&key={api_key}"
        calculated = hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()
        return calculated == sign
    except Exception as exc:
        logger.error("wechat_sign_verify_failed", error=str(exc))
        return False


def verify_alipay_sign(body: dict[str, Any], sign: str, alipay_public_key: str) -> bool:
    try:
        public_key = load_pem_public_key(alipay_public_key.encode("utf-8"))
        sorted_keys = sorted(body.keys())
        sign_str = "&".join(f"{k}={body[k]}" for k in sorted_keys)
        sign_bytes = base64.b64decode(sign)
        public_key.verify(
            sign_bytes,
            sign_str.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as exc:
        logger.error("alipay_sign_verify_failed", error=str(exc))
        return False


def parse_wechat_xml(xml_data: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_data)
    params: dict[str, str] = {}
    for child in root:
        params[child.tag] = child.text or ""
    return params


def _retrieve_alipay_public_key() -> str | None:
    path = settings.alipay_public_key_path
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        logger.error("load_alipay_public_key_failed", path=path, error=str(exc))
        return None


@router.post("/callback")
async def payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    sign_type = request.headers.get("X-Sign-Type", "").upper()
    header_signature = request.headers.get("X-Signature", "")

    raw_body = await request.body()
    if not raw_body:
        logger.warning("callback_empty_body")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "FAIL", "message": "empty request body"},
        )

    if sign_type == "MD5":
        return await _handle_wechat_callback(db, raw_body)
    elif sign_type == "RSA2":
        return await _handle_alipay_callback(db, raw_body, header_signature)
    else:
        content_type = request.headers.get("content-type", "").lower()
        if "xml" in content_type:
            return await _handle_wechat_callback(db, raw_body)
        else:
            return await _handle_alipay_callback(db, raw_body, header_signature)


async def _handle_wechat_callback(
    db: AsyncSession,
    raw_body: bytes,
) -> JSONResponse:
    try:
        params = parse_wechat_xml(raw_body)
    except Exception as exc:
        logger.error("wechat_xml_parse_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "FAIL", "message": "invalid xml"},
        )

    wechat_sign = params.pop("sign", "")
    if not wechat_sign:
        logger.warning("wechat_callback_missing_sign")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "FAIL", "message": "missing sign"},
        )

    api_key = settings.wechat_api_key
    if not api_key:
        logger.error("wechat_api_key_not_configured")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "FAIL", "message": "server configuration error"},
        )

    if not verify_wechat_sign(params, wechat_sign, api_key):
        logger.warning("wechat_sign_verify_failed", order_no=params.get("out_trade_no"))
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"code": "FAIL", "message": "signature verification failed"},
        )

    result_code = params.get("result_code", "")
    if result_code.upper() != "SUCCESS":
        logger.info("wechat_payment_not_success", result_code=result_code)
        return JSONResponse(
            content={"code": "SUCCESS", "message": "ok"},
        )

    order_no = params.get("out_trade_no", "")
    transaction_id = params.get("transaction_id", "")
    total_fee_str = params.get("total_fee", "0")

    return await _process_payment(
        db=db,
        order_no=order_no,
        transaction_id=transaction_id,
        amount_from_platform=Decimal(total_fee_str) / Decimal("100"),
        payment_method=PaymentMethod.WECHAT,
    )


async def _handle_alipay_callback(
    db: AsyncSession,
    raw_body: bytes,
    signature: str,
) -> JSONResponse:
    if not signature:
        logger.warning("alipay_callback_missing_signature")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "FAIL", "message": "missing signature"},
        )

    try:
        import json
        body = json.loads(raw_body)
    except Exception as exc:
        logger.error("alipay_json_parse_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "FAIL", "message": "invalid json"},
        )

    alipay_public_key = _retrieve_alipay_public_key()
    if not alipay_public_key:
        logger.error("alipay_public_key_not_configured")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "FAIL", "message": "server configuration error"},
        )

    if not verify_alipay_sign(body, signature, alipay_public_key):
        logger.warning("alipay_sign_verify_failed", order_no=body.get("out_trade_no"))
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"code": "FAIL", "message": "signature verification failed"},
        )

    trade_status = body.get("trade_status", "")
    if trade_status.upper() not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        logger.info("alipay_trade_not_success", trade_status=trade_status)
        return JSONResponse(
            content={"code": "SUCCESS", "message": "ok"},
        )

    order_no = body.get("out_trade_no", "")
    transaction_id = body.get("trade_no", "")
    total_amount_str = body.get("total_amount", "0")

    return await _process_payment(
        db=db,
        order_no=order_no,
        transaction_id=transaction_id,
        amount_from_platform=Decimal(total_amount_str),
        payment_method=PaymentMethod.ALIPAY,
    )


async def _process_payment(
    db: AsyncSession,
    order_no: str,
    transaction_id: str,
    amount_from_platform: Decimal,
    payment_method: PaymentMethod,
) -> JSONResponse:
    if not order_no:
        logger.warning("callback_missing_order_no")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "FAIL", "message": "missing order_no"},
        )

    result = await db.execute(
        select(Order).where(Order.order_no == order_no)
    )
    order = result.scalar_one_or_none()

    if order is None:
        logger.error("order_not_found", order_no=order_no)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"code": "FAIL", "message": "order not found"},
        )

    if order.status == OrderStatus.PAID:
        logger.info("order_already_paid", order_no=order_no)
        return JSONResponse(
            content={"code": "SUCCESS", "message": "ok"},
        )

    expected_amount = Decimal(str(order.amount_cny))
    if amount_from_platform != expected_amount:
        logger.error(
            "amount_mismatch",
            order_no=order_no,
            expected=str(expected_amount),
            received=str(amount_from_platform),
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "FAIL", "message": "amount mismatch"},
        )

    order.status = OrderStatus.PAID
    order.transaction_id = transaction_id
    order.paid_at = datetime.now(timezone.utc)

    tier = QuotaTier(order.tier.value)

    quota_result = await db.execute(
        select(Quota).where(Quota.user_id == order.user_id).with_for_update()
    )
    quota = quota_result.scalar_one_or_none()

    if quota is None:
        config = TIER_CONFIG.get(tier, {"monthly_pages": 30, "daily_pages": 5})
        quota = Quota(
            user_id=order.user_id,
            tier=tier,
            monthly_pages=config["monthly_pages"],
            daily_pages=config["daily_pages"],
            used_pages=0,
            used_daily_pages=0,
        )
        db.add(quota)
    else:
        config = TIER_CONFIG.get(tier, {"monthly_pages": 30, "daily_pages": 5})
        quota.tier = tier
        quota.monthly_pages = config["monthly_pages"]
        quota.daily_pages = config["daily_pages"]

    await db.commit()

    logger.info(
        "payment_callback_processed",
        order_no=order_no,
        transaction_id=transaction_id,
        tier=tier.value,
        payment_method=payment_method.value,
    )

    return JSONResponse(
        content={"code": "SUCCESS", "message": "ok"},
    )
