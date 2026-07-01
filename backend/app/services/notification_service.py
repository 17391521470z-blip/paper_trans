from __future__ import annotations

import asyncio
import json
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage as _StdEmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)


@dataclass(slots=True)
class SMSMessage:
    phone: str
    template_code: str
    template_params: dict[str, Any]
    sign_name: str | None = None


@dataclass(slots=True)
class EmailMessage:
    to: str
    subject: str
    body: str
    is_html: bool = False


@dataclass(slots=True)
class WebhookMessage:
    content: str
    mentioned_mobile: list[str] | None = None


def _dev_mode() -> bool:
    return settings.app_env in {"development", "test"} or settings.sms_provider == "mock"


def _is_aliyun_configured() -> bool:
    return bool(
        settings.sms_provider == "aliyun"
        and settings.sms_access_key_id
        and settings.sms_access_key_secret
        and settings.sms_template_code
    )


def _is_smtp_configured() -> bool:
    return bool(
        settings.smtp_host
        and settings.smtp_username
        and settings.smtp_password
        and settings.smtp_from_email
    )


def _is_wecom_configured() -> bool:
    return bool(settings.wecom_webhook_url)


def _serialize_template(params: dict[str, Any]) -> str:
    return json.dumps(params, ensure_ascii=False)


async def _send_aliyun_sms_via_sdk(message: SMSMessage) -> bool:
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest
    except ImportError:
        logger.warning("sms.aliyun_sdk_missing")
        return False

    def _call() -> bool:
        try:
            client = AcsClient(
                settings.sms_access_key_id,
                settings.sms_access_key_secret,
                settings.oss_region or "cn-hangzhou",
            )
            request = CommonRequest()
            request.set_accept_format("JSON")
            request.set_domain("dysmsapi.aliyuncs.com")
            request.set_method("POST")
            request.set_protocol_type("https")
            request.set_version("2017-05-25")
            request.set_action_name("SendSms")
            request.add_query_param("PhoneNumbers", message.phone)
            request.add_query_param(
                "SignName", message.sign_name or settings.sms_sign_name
            )
            request.add_query_param(
                "TemplateCode", message.template_code or settings.sms_template_code
            )
            request.add_query_param("TemplateParam", _serialize_template(message.template_params))
            response = client.do_action_with_exception(request)
            if isinstance(response, (bytes, bytearray)):
                response = response.decode("utf-8", errors="replace")
            payload = json.loads(response)
            return str(payload.get("Code", "")).upper() == "OK"
        except Exception as exc:
            logger.warning("sms.aliyun_call_failed", error=str(exc))
            return False

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _call)


async def _send_aliyun_sms_via_http(message: SMSMessage) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://dysmsapi.aliyuncs.com/",
                data={
                    "PhoneNumbers": message.phone,
                    "SignName": message.sign_name or settings.sms_sign_name,
                    "TemplateCode": message.template_code or settings.sms_template_code,
                    "TemplateParam": _serialize_template(message.template_params),
                    "AccessKeyId": settings.sms_access_key_id,
                },
            )
            return response.status_code == 200
    except Exception as exc:
        logger.warning("sms.aliyun_http_failed", error=str(exc))
        return False


async def send_sms(message: SMSMessage) -> bool:
    if _dev_mode() or not _is_aliyun_configured():
        logger.warning(
            "sms.degraded",
            phone=message.phone,
            reason="aliyun_not_configured",
            provider=settings.sms_provider,
        )
        return False
    sdk_result = await _send_aliyun_sms_via_sdk(message)
    if sdk_result:
        return True
    return await _send_aliyun_sms_via_http(message)


def _send_smtp_sync(message: EmailMessage) -> bool:
    if not _is_smtp_configured():
        return False
    try:
        smtp_msg = MIMEMultipart("alternative") if message.is_html else MIMEText(message.body, "plain", "utf-8")
        if isinstance(smtp_msg, MIMEMultipart):
            if message.is_html:
                smtp_msg.attach(MIMEText(message.body, "html", "utf-8"))
            else:
                smtp_msg.attach(MIMEText(message.body, "plain", "utf-8"))
        smtp_msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        smtp_msg["To"] = message.to
        smtp_msg["Subject"] = message.subject

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, [message.to], smtp_msg.as_string())
        return True
    except Exception as exc:
        logger.warning("email.smtp_failed", error=str(exc))
        return False


async def send_email(message: EmailMessage) -> bool:
    if not _is_smtp_configured():
        logger.warning("email.degraded", reason="smtp_not_configured")
        return False
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _send_smtp_sync, message)


async def send_wecom_webhook(message: WebhookMessage) -> bool:
    if not _is_wecom_configured():
        logger.warning("wecom.degraded", reason="webhook_not_configured")
        return False
    payload: dict[str, Any] = {
        "msgtype": "text",
        "text": {"content": message.content},
    }
    if message.mentioned_mobile:
        payload["text"]["mentioned_mobile_list"] = message.mentioned_mobile
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(settings.wecom_webhook_url, json=payload)
            if response.status_code != 200:
                logger.warning(
                    "wecom.webhook_non_2xx",
                    status=response.status_code,
                    body=response.text[:200],
                )
            return response.status_code == 200
    except Exception as exc:
        logger.warning("wecom.webhook_failed", error=str(exc))
        return False


def send_sms_code(phone: str, code: str, ttl_seconds: int = 300) -> bool:
    if _is_aliyun_configured():
        message = SMSMessage(
            phone=phone,
            template_code=settings.sms_template_code,
            template_params={"code": code, "minutes": str(ttl_seconds // 60 or 5)},
            sign_name=settings.sms_sign_name,
        )
        schedule_fire_and_forget(send_sms(message))
        return True
    logger.warning("sms.dev_mode_fallback", phone=phone, code=code)
    return False


def send_email_code(to: str, code: str, ttl_seconds: int = 300) -> bool:
    minutes = max(ttl_seconds // 60, 1)
    body = (
        f"您的验证码为：{code}\n"
        f"验证码 {minutes} 分钟内有效，请勿泄露给他人。\n"
        f"如非本人操作，请忽略本邮件。\n"
        f"—— Paper Translate"
    )
    message = EmailMessage(
        to=to,
        subject="Paper Translate 注册验证码",
        body=body,
        is_html=False,
    )
    schedule_fire_and_forget(send_email(message))
    return True


def send_sms_simple(phone: str, code: str) -> bool:
    return send_sms_code(phone, code, ttl_seconds=settings.sms_code_expire_seconds)


def send_email_simple(to: str, subject: str, body: str) -> bool:
    message = EmailMessage(to=to, subject=subject, body=body, is_html=False)
    schedule_fire_and_forget(send_email(message))
    return True


async def notify_cost_alert(current_cost_cny: float, threshold_cny: float) -> bool:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return await send_wecom_webhook(
        WebhookMessage(
            content=(
                f"[LLM 成本告警] {ts}\n"
                f"当日累计成本：¥{current_cost_cny:.2f}\n"
                f"阈值：¥{threshold_cny:.2f}\n"
                f"请关注用量并考虑切换模型或限流。"
            ),
            mentioned_mobile=(
                [settings.wecom_webhook_mentioned_mobile]
                if settings.wecom_webhook_mentioned_mobile
                else None
            ),
        )
    )


def schedule_fire_and_forget(coro: Any) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(coro)