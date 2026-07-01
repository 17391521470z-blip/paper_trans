from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import verify_token
from app.models.quota import Quota, QuotaTier
from app.models.user import User


logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False, description="JWT Bearer token")


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供鉴权凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌缺少主体信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌主体格式不合法",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号不存在或已被删除",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用，请联系管理员",
        )
    return user


async def _load_user_quota(db: AsyncSession, user_id: uuid.UUID) -> Quota | None:
    stmt = select(Quota).where(Quota.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _maybe_rollover_quota(quota: Quota) -> Quota:
    now = datetime.now(timezone.utc)
    if quota.reset_at is not None and now >= quota.reset_at:
        quota.used_pages = 0
        if now.month == 12:
            quota.reset_at = now.replace(
                year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            quota.reset_at = now.replace(
                month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
    if quota.daily_reset_at is not None and now >= quota.daily_reset_at:
        quota.used_daily_pages = 0
        quota.daily_reset_at = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return quota


def require_quota(min_pages: int = 1):
    async def _checker(
        db: Annotated[AsyncSession, Depends(get_db)],
        user: Annotated[User, Depends(get_current_active_user)],
    ) -> tuple[User, Quota]:
        if min_pages < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="配额预检参数非法",
            )
        quota = await _load_user_quota(db, user.id)
        if quota is None:
            quota = Quota(
                user_id=user.id,
                tier=QuotaTier.FREE,
                monthly_pages=30,
                daily_pages=5,
                used_pages=0,
                used_daily_pages=0,
                reset_at=None,
                daily_reset_at=None,
            )
            db.add(quota)
            await db.commit()
            await db.refresh(quota)

        quota = await _maybe_rollover_quota(quota)
        await db.commit()
        await db.refresh(quota)

        remaining_monthly = max(quota.monthly_pages - quota.used_pages, 0)
        remaining_daily = max(quota.daily_pages - quota.used_daily_pages, 0)
        if remaining_monthly < min_pages:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="本月翻译页数已用完，请升级套餐或下月再来",
                headers={
                    "X-Quota-Monthly-Limit": str(quota.monthly_pages),
                    "X-Quota-Monthly-Used": str(quota.used_pages),
                    "X-Quota-Reason": "monthly_quota_exceeded",
                },
            )
        if remaining_daily < min_pages:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日翻译页数已用完，请明天再来或升级套餐",
                headers={
                    "X-Quota-Daily-Limit": str(quota.daily_pages),
                    "X-Quota-Daily-Used": str(quota.used_daily_pages),
                    "X-Quota-Reason": "daily_quota_exceeded",
                },
            )
        return user, quota

    return _checker


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def _load_quota(db: AsyncSession, user_id: uuid.UUID) -> Quota:
    quota = await _load_user_quota(db, user_id)
    if quota is None:
        quota = Quota(
            user_id=user_id,
            tier=QuotaTier.FREE,
            monthly_pages=30,
            daily_pages=5,
            used_pages=0,
            used_daily_pages=0,
            reset_at=None,
            daily_reset_at=None,
        )
        db.add(quota)
        await db.flush()
    return quota


async def get_current_user_from_token(
    token: str,
    db: AsyncSession,
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authentication token",
        )
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        )
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token missing subject",
        )
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid subject in token",
        ) from exc
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user no longer exists",
        )
    return user