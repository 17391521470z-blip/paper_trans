from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentActiveUser
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.quota import Quota, QuotaTier, tier_default_pages
from app.models.user import User
from app.schemas.quota import QuotaResponse
from app.services.quota_service import check_quota


logger = get_logger(__name__)

router: APIRouter = APIRouter()


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _next_month_first(now: datetime) -> datetime:
    if now.month == 12:
        return now.replace(
            year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return now.replace(
        month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _next_day_zero(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def _load_quota(db: AsyncSession, user_id) -> Quota | None:
    stmt = select(Quota).where(Quota.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _ensure_quota(db: AsyncSession, user: User) -> Quota:
    quota = await _load_quota(db, user.id)
    if quota is None:
        monthly_pages, daily_pages = tier_default_pages(QuotaTier.FREE)
        now = datetime.now(timezone.utc)
        quota = Quota(
            user_id=user.id,
            tier=QuotaTier.FREE,
            monthly_pages=monthly_pages,
            daily_pages=daily_pages,
            used_pages=0,
            used_daily_pages=0,
            reset_at=_next_month_first(now),
            daily_reset_at=_next_day_zero(now),
        )
        db.add(quota)
        await db.commit()
        await db.refresh(quota)
    return quota


async def _maybe_rollover(db: AsyncSession, quota: Quota) -> Quota:
    now = datetime.now(timezone.utc)
    dirty = False
    if quota.reset_at is not None and now >= _ensure_aware(quota.reset_at):
        quota.used_pages = 0
        quota.reset_at = _next_month_first(now)
        dirty = True
    if quota.daily_reset_at is not None and now >= _ensure_aware(quota.daily_reset_at):
        quota.used_daily_pages = 0
        quota.daily_reset_at = _next_day_zero(now)
        dirty = True
    if dirty:
        await db.commit()
        await db.refresh(quota)
    return quota


def _to_response(quota: Quota) -> QuotaResponse:
    remaining_pages = max(quota.monthly_pages - quota.used_pages, 0)
    remaining_daily = max(quota.daily_pages - quota.used_daily_pages, 0)
    return QuotaResponse(
        tier=quota.tier.value if hasattr(quota.tier, "value") else str(quota.tier),
        monthly_pages=quota.monthly_pages,
        used_pages=quota.used_pages,
        remaining_pages=remaining_pages,
        daily_pages=quota.daily_pages,
        used_daily_pages=quota.used_daily_pages,
        remaining_daily_pages=remaining_daily,
        reset_at=quota.reset_at,
        daily_reset_at=quota.daily_reset_at,
    )


@router.get(
    "",
    response_model=QuotaResponse,
    summary="获取当前用户的翻译配额",
)
async def get_quota(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUser,
) -> QuotaResponse:
    quota = await _ensure_quota(db, current_user)
    quota = await _maybe_rollover(db, quota)
    return _to_response(quota)


@router.get(
    "/check",
    summary="预检：当前用户是否还有可用配额（默认查询 1 页）",
)
async def check_my_quota(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUser,
    pages: int = 1,
) -> dict:
    if pages < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="查询页数必须 >= 1",
        )
    quota = await _ensure_quota(db, current_user)
    quota = await _maybe_rollover(db, quota)

    result = check_quota(
        tier=quota.tier,
        used_pages=quota.used_pages,
        monthly_pages=quota.monthly_pages,
        used_daily_pages=quota.used_daily_pages,
        daily_pages=quota.daily_pages,
        requested_pages=pages,
    )
    return {
        "allowed": result.allowed,
        "reason": result.reason,
        "requested_pages": pages,
        "remaining_monthly": result.remaining_monthly,
        "remaining_daily": result.remaining_daily,
        "tier": quota.tier.value if hasattr(quota.tier, "value") else str(quota.tier),
        "monthly_limit": quota.monthly_pages,
        "daily_limit": quota.daily_pages,
        "used_monthly": quota.used_pages,
        "used_daily": quota.used_daily_pages,
        "reset_at": quota.reset_at.isoformat() if quota.reset_at else None,
        "daily_reset_at": quota.daily_reset_at.isoformat() if quota.daily_reset_at else None,
    }