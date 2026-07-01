from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentActiveUser
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, SendCodeRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services import auth_service


logger = get_logger(__name__)

router: APIRouter = APIRouter()


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class AuthResponse(BaseModel):
    model_config = ConfigDict()

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


def _serialize_user(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        phone=user.phone,
        email=user.email,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


@router.post(
    "/send-code",
    response_model=None,
    summary="发送注册/登录验证码",
)
async def send_code(
    payload: SendCodeRequest,
) -> dict[str, Any]:
    if payload.account_type not in {"phone", "email"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="账号类型必须为 phone 或 email",
        )
    result = await auth_service.send_verification_code(
        payload.account,
        channel="sms" if payload.account_type == "phone" else "email",
    )
    return result


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册新用户（手机号/邮箱）",
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    user = await auth_service.register_user(db, payload)
    token = auth_service.create_user_session(user)
    return AuthResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
        user=_serialize_user(user),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="账号登录（手机号/邮箱 + 密码）",
)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    user, token = await auth_service.login_user(db, payload)
    return AuthResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
        user=_serialize_user(user),
    )


@router.post(
    "/logout",
    summary="登出（前端丢弃 Token 即可，此端点仅供日志/审计）",
)
async def logout(
    current_user: CurrentActiveUser,
) -> dict[str, Any]:
    logger.info("auth.user_logout", user_id=str(current_user.id))
    return {
        "success": True,
        "message": "已登出，请清除本地 Token",
        "logged_out_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post(
    "/change-password",
    summary="修改当前账号密码",
)
async def change_password(
    payload: ChangePasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUser,
) -> dict[str, Any]:
    ok = await auth_service.change_password(
        db, current_user, payload.old_password, payload.new_password
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码修改失败",
        )
    new_token = auth_service.create_user_session(current_user)
    return {
        "success": True,
        "message": "密码已更新",
        "access_token": new_token.access_token,
        "expires_in": new_token.expires_in,
    }


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="使用当前 access_token 换取新 token（即将过期续期）",
)
async def refresh_token(
    current_user: CurrentActiveUser,
) -> TokenResponse:
    return auth_service.create_user_session(current_user)