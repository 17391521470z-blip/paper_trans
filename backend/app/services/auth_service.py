from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis_client import redis_client
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.quota import Quota, QuotaTier, tier_default_pages
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, SendCodeRequest, TokenResponse
from app.services.notification_service import (
    send_email_code,
    send_sms_code,
)


settings = get_settings()
logger = get_logger(__name__)


_PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,14}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VERIFY_CODE_KEY = "verify_code:{contact}"
VERIFY_CODE_SENT_KEY = "verify_code_sent:{contact}"
VERIFY_CODE_ATTEMPT_KEY = "verify_code_attempt:{contact}"

DEV_VERIFICATION_CODE = "123456"

DEFAULT_PHONE_COOLDOWN_SECONDS = 60
MAX_VERIFY_ATTEMPTS = 5


def detect_account_type(account: str) -> str:
    if _PHONE_PATTERN.match(account):
        return "phone"
    if _EMAIL_PATTERN.match(account):
        return "email"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="账号格式不合法，需为手机号或邮箱",
    )


def hash_password(plain_password: str) -> str:
    if not plain_password or len(plain_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码至少 8 位",
        )
    return get_password_hash(plain_password)


def check_password(plain_password: str, password_hash: str) -> bool:
    return verify_password(plain_password, password_hash)


def generate_verification_code(length: int = 6) -> str:
    if length < 4 or length > 12:
        raise ValueError("code length must be between 4 and 12")
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def _next_month_reset(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.month == 12:
        return current.replace(
            year=current.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return current.replace(
        month=current.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _next_day_reset(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _verify_code_key(contact: str) -> str:
    return VERIFY_CODE_KEY.format(contact=contact)


def _verify_sent_key(contact: str) -> str:
    return VERIFY_CODE_SENT_KEY.format(contact=contact)


def _verify_attempt_key(contact: str) -> str:
    return VERIFY_CODE_ATTEMPT_KEY.format(contact=contact)


def _normalize_account(account: str, account_type: str) -> str:
    value = account.strip()
    if account_type == "phone":
        if not _PHONE_PATTERN.match(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号格式不合法",
            )
    elif account_type == "email":
        if not _EMAIL_PATTERN.match(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱格式不合法",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="账号类型必须为 phone 或 email",
        )
    return value.lower()


async def _find_user_by_account(db: AsyncSession, account: str, account_type: str | None = None) -> User | None:
    if account_type == "phone":
        stmt = select(User).where(User.phone == account)
    elif account_type == "email":
        stmt = select(User).where(User.email == account)
    else:
        stmt = select(User).where(or_(User.phone == account, User.email == account))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def register_user(db: AsyncSession, request: RegisterRequest) -> User:
    account = _normalize_account(request.account, request.account_type)
    password_hash = hash_password(request.password)
    phone = account if request.account_type == "phone" else None
    email = account if request.account_type == "email" else None

    existing = await _find_user_by_account(db, account, request.account_type)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该手机号/邮箱已被注册",
        )

    await _consume_verification_code(account, request.code, delete_on_success=True)

    user = User(
        phone=phone,
        email=email,
        password_hash=password_hash,
        nickname=request.nickname,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("auth.register_conflict", account=account, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该手机号/邮箱已被注册",
        ) from exc

    monthly_pages, daily_pages = tier_default_pages(QuotaTier.FREE)
    quota = Quota(
        user_id=user.id,
        tier=QuotaTier.FREE,
        monthly_pages=monthly_pages,
        daily_pages=daily_pages,
        used_pages=0,
        used_daily_pages=0,
        reset_at=_next_month_reset(),
        daily_reset_at=_next_day_reset(),
    )
    db.add(quota)
    await db.commit()
    await db.refresh(user)
    logger.info("auth.user_registered", user_id=str(user.id), account_type=request.account_type)
    return user


async def authenticate_user(
    db: AsyncSession,
    identifier: str,
    password: str,
) -> User | None:
    if not identifier or not password:
        return None

    try:
        account_type = detect_account_type(identifier)
    except HTTPException:
        return None
    normalized = identifier.strip().lower() if account_type == "email" else identifier.strip()
    user = await _find_user_by_account(db, normalized, account_type)
    if user is None or not user.is_active:
        return None
    if not check_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


def create_user_session(user: User, *, token_type: str = "access") -> TokenResponse:
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "type": token_type,
    }
    if user.phone:
        payload["phone"] = user.phone
    if user.email:
        payload["email"] = user.email
    token = create_access_token(payload)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        user_id=str(user.id),
    )


async def _generate_and_store_code(contact: str, account_type: str) -> str:
    code = generate_verification_code(settings.verify_code_length)
    try:
        ttl = settings.verify_code_expire_seconds
        await redis_client.set(_verify_code_key(contact), code, ex=ttl)
        await redis_client.set(
            _verify_sent_key(contact),
            datetime.now(timezone.utc).isoformat(),
            ex=DEFAULT_PHONE_COOLDOWN_SECONDS,
        )
        await redis_client.delete(_verify_attempt_key(contact))
    except Exception as exc:
        logger.warning("auth.redis_unavailable_for_code", error=str(exc))
    return code


async def send_verification_code(
    contact: str,
    channel: str = "sms",
) -> dict[str, Any]:
    normalized = _normalize_account(contact, channel)
    if channel not in {"sms", "email"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channel 必须为 sms 或 email",
        )

    code = await _generate_and_store_code(normalized, channel)
    delivered = False
    if channel == "sms":
        delivered = send_sms_code(normalized, code, ttl_seconds=settings.verify_code_expire_seconds)
    else:
        delivered = send_email_code(normalized, code, ttl_seconds=settings.verify_code_expire_seconds)

    response: dict[str, Any] = {
        "success": True,
        "channel": channel,
        "contact": normalized,
        "delivered": delivered,
        "expires_in": settings.verify_code_expire_seconds,
    }
    if not delivered and settings.app_env in {"development", "test"}:
        response["dev_code"] = DEV_VERIFICATION_CODE
        response["hint"] = "未配置真实短信/邮件通道，使用开发验证码"
    return response


async def send_verification_code_from_request(
    db: AsyncSession,
    request: SendCodeRequest,
) -> dict[str, Any]:
    if request.account_type == "phone":
        channel = "sms"
    else:
        channel = "email"
    return await send_verification_code(request.account, channel=channel)


async def _consume_verification_code(
    contact: str,
    code: str,
    *,
    delete_on_success: bool = True,
) -> bool:
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码不能为空",
        )

    attempt_key = _verify_attempt_key(contact)
    try:
        attempts = await redis_client.incr(attempt_key)
        if attempts == 1:
            await redis_client.expire(attempt_key, settings.verify_code_expire_seconds)
        if attempts > MAX_VERIFY_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="验证码尝试次数过多，请稍后再试",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("auth.redis_attempt_track_failed", error=str(exc))

    if code == DEV_VERIFICATION_CODE and settings.app_env in {"development", "test"}:
        try:
            await redis_client.delete(_verify_code_key(contact))
            await redis_client.delete(attempt_key)
        except Exception:
            pass
        return True

    stored_code = None
    try:
        stored_code = await redis_client.get(_verify_code_key(contact))
    except Exception as exc:
        logger.warning("auth.redis_get_failed", error=str(exc))

    if not stored_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码已过期或不存在，请重新获取",
        )
    if str(stored_code) != str(code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误",
        )

    if delete_on_success:
        try:
            await redis_client.delete(_verify_code_key(contact))
            await redis_client.delete(attempt_key)
        except Exception:
            pass
    return True


async def change_password(
    db: AsyncSession,
    user: User,
    old_password: str,
    new_password: str,
) -> bool:
    if not old_password or not new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码和新密码不能为空",
        )
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码至少 8 位",
        )
    if not check_password(old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码不正确",
        )
    user.password_hash = hash_password(new_password)
    await db.commit()
    await db.refresh(user)
    logger.info("auth.password_changed", user_id=str(user.id))
    return True


async def login_user(db: AsyncSession, request: LoginRequest) -> tuple[User, TokenResponse]:
    identifier = request.account.strip()
    if request.account_type == "auto":
        try:
            account_type = detect_account_type(identifier)
        except HTTPException as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc.detail),
            ) from exc
    else:
        account_type = request.account_type
        if account_type == "phone":
            if not _PHONE_PATTERN.match(identifier):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="手机号格式不合法",
                )
        elif account_type == "email":
            if not _EMAIL_PATTERN.match(identifier.lower()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="邮箱格式不合法",
                )

    user = await authenticate_user(db, identifier, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        )
    token = create_user_session(user)
    return user, token


async def update_user_profile(
    db: AsyncSession,
    user: User,
    *,
    nickname: str | None = None,
    email: str | None = None,
    avatar_url: str | None = None,
) -> User:
    updated = False
    if nickname is not None:
        nickname = nickname.strip()
        if nickname and nickname != user.nickname:
            user.nickname = nickname
            updated = True
    if email is not None:
        normalized_email = email.strip().lower()
        if not _EMAIL_PATTERN.match(normalized_email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱格式不合法",
            )
        if normalized_email != (user.email or "").lower():
            existing = await _find_user_by_account(db, normalized_email, "email")
            if existing is not None and existing.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="该邮箱已被其他账号使用",
                )
            user.email = normalized_email
            updated = True
    if avatar_url is not None:
        if avatar_url != user.avatar_url:
            user.avatar_url = avatar_url
            updated = True

    if updated:
        try:
            await db.commit()
            await db.refresh(user)
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="信息更新冲突，请重试",
            ) from exc
    return user


async def deactivate_user(db: AsyncSession, user: User) -> bool:
    user.is_active = False
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("auth.deactivate_failed", user_id=str(user.id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="账号停用失败，请稍后重试",
        ) from exc
    logger.info("auth.user_deactivated", user_id=str(user.id))
    return True


def build_access_token(
    user_id: uuid.UUID,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    expire_seconds = int(
        (expires_delta or timedelta(minutes=settings.jwt_expire_minutes)).total_seconds()
    )
    token = create_access_token(payload, expires_delta=expires_delta)
    return token, expire_seconds


def build_refresh_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
    }
    return create_access_token(payload, expires_delta=timedelta(days=7))


def issue_token_pair(user_id: uuid.UUID) -> dict[str, Any]:
    access_token, expires_in = build_access_token(user_id)
    refresh_token = build_refresh_token(user_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "user_id": str(user_id),
    }