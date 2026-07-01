from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentActiveUser
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.user import UserResponse
from app.services import auth_service


logger = get_logger(__name__)

router: APIRouter = APIRouter()


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    avatar_url: str | None = Field(default=None, max_length=512)


class DeleteUserResponse(BaseModel):
    success: bool = True
    message: str
    deactivated_at: datetime


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


@router.get(
    "/me",
    response_model=UserResponse,
    summary="获取当前登录用户信息",
)
async def get_me(
    current_user: CurrentActiveUser,
) -> UserResponse:
    return _serialize_user(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="更新当前用户的昵称/邮箱/头像",
)
async def update_me(
    payload: UpdateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUser,
) -> UserResponse:
    if payload.nickname is None and payload.email is None and payload.avatar_url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少提供一个需要更新的字段",
        )

    updated = await auth_service.update_user_profile(
        db,
        current_user,
        nickname=payload.nickname,
        email=str(payload.email) if payload.email else None,
        avatar_url=payload.avatar_url,
    )
    logger.info("user.profile_updated", user_id=str(updated.id))
    return _serialize_user(updated)


@router.delete(
    "/me",
    response_model=DeleteUserResponse,
    summary="软删除当前账号（is_active=false）",
)
async def delete_me(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUser,
) -> DeleteUserResponse:
    await auth_service.deactivate_user(db, current_user)
    return DeleteUserResponse(
        success=True,
        message="账号已停用，相关数据保留 30 天后可联系管理员彻底删除",
        deactivated_at=datetime.now(timezone.utc),
    )