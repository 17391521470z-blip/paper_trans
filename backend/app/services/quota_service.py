from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.quota import QuotaTier


@dataclass(slots=True)
class QuotaCheckResult:
    allowed: bool
    reason: str | None
    remaining_monthly: int
    remaining_daily: int


@dataclass(slots=True)
class QuotaConsumeResult:
    consumed: bool
    new_used_pages: int
    new_used_daily_pages: int
    reason: str | None = None


DEFAULT_TIER_PAGES: dict[QuotaTier, tuple[int, int]] = {
    QuotaTier.FREE: (30, 5),
    QuotaTier.STANDARD: (200, 50),
    QuotaTier.PRO: (800, 150),
}


def tier_default_pages(tier: QuotaTier) -> tuple[int, int]:
    return DEFAULT_TIER_PAGES.get(tier, DEFAULT_TIER_PAGES[QuotaTier.FREE])


def check_quota(
    *,
    tier: QuotaTier,
    used_pages: int,
    monthly_pages: int,
    used_daily_pages: int,
    daily_pages: int,
    requested_pages: int = 1,
) -> QuotaCheckResult:
    if requested_pages < 1:
        return QuotaCheckResult(False, "requested_pages must be >= 1", 0, 0)

    remaining_monthly = max(monthly_pages - used_pages, 0)
    remaining_daily = max(daily_pages - used_daily_pages, 0)

    if remaining_monthly < requested_pages:
        return QuotaCheckResult(
            allowed=False,
            reason="monthly_quota_exceeded",
            remaining_monthly=remaining_monthly,
            remaining_daily=remaining_daily,
        )
    if remaining_daily < requested_pages:
        return QuotaCheckResult(
            allowed=False,
            reason="daily_quota_exceeded",
            remaining_monthly=remaining_monthly,
            remaining_daily=remaining_daily,
        )
    return QuotaCheckResult(
        allowed=True,
        reason=None,
        remaining_monthly=remaining_monthly,
        remaining_daily=remaining_daily,
    )


def consume_quota(
    *,
    user_id: uuid.UUID,
    used_pages: int,
    used_daily_pages: int,
    requested_pages: int = 1,
) -> QuotaConsumeResult:
    _ = user_id
    if requested_pages < 1:
        return QuotaConsumeResult(
            consumed=False,
            new_used_pages=used_pages,
            new_used_daily_pages=used_daily_pages,
            reason="invalid_requested_pages",
        )
    return QuotaConsumeResult(
        consumed=True,
        new_used_pages=used_pages + requested_pages,
        new_used_daily_pages=used_daily_pages + requested_pages,
    )


def upgrade_target_pages(tier: QuotaTier) -> tuple[int, int]:
    return tier_default_pages(tier)
