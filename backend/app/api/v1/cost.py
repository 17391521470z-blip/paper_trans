from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession, get_current_active_user
from app.models.user import User
from app.services.cost_monitor_service import (
    check_daily_alert,
    get_daily_cost,
    top_spenders,
)


router: APIRouter = APIRouter()


class DailyCostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    total_cost_cny: float
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    unique_users: int
    threshold_cny: float
    exceeded: bool


class TopSpenderEntry(BaseModel):
    user_id: str
    total_cost_cny: float
    task_count: int


class TopSpendersResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    items: list[TopSpenderEntry] = Field(default_factory=list)


@router.get(
    "/today",
    response_model=DailyCostResponse,
    summary="查看当日 LLM 累计成本（self or admin）",
)
async def get_today_cost(
    db: DbSession,
    user: User = Depends(get_current_active_user),
    threshold_cny: float | None = Query(default=None, ge=0),
) -> DailyCostResponse:
    summary = await get_daily_cost(db)
    from app.core.config import get_settings

    settings = get_settings()
    threshold = float(threshold_cny or settings.llm_daily_cost_limit_cny)
    return DailyCostResponse(
        date=summary.date,
        total_cost_cny=float(summary.total_cost_cny),
        call_count=summary.call_count,
        prompt_tokens=summary.prompt_tokens,
        completion_tokens=summary.completion_tokens,
        unique_users=summary.unique_users,
        threshold_cny=threshold,
        exceeded=float(summary.total_cost_cny) > threshold,
    )


@router.get(
    "/alert",
    summary="手动触发当日成本告警检测",
)
async def check_alert(
    db: DbSession,
    user: User = Depends(get_current_active_user),
    threshold_cny: float | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    triggered = await check_daily_alert(db, threshold_cny=threshold_cny)
    summary = await get_daily_cost(db)
    return {
        "triggered": triggered,
        "total_cost_cny": float(summary.total_cost_cny),
        "date": summary.date.isoformat(),
    }


@router.get(
    "/top-spenders",
    response_model=TopSpendersResponse,
    summary="查看当日花费 Top 用户（admin only）",
)
async def get_top_spenders(
    db: DbSession,
    user: User = Depends(get_current_active_user),
    target_date: date | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=50),
) -> TopSpendersResponse:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "user_disabled"},
        )
    spenders = await top_spenders(db, day=target_date, limit=limit)
    target = target_date or date.today()
    return TopSpendersResponse(
        date=target,
        items=[TopSpenderEntry(**entry) for entry in spenders],
    )


__all__ = ["router"]