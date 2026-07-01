from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.task import Task, TaskStatus
from app.services.notification_service import notify_cost_alert


settings = get_settings()
logger = get_logger(__name__)


@dataclass(slots=True)
class DailyCostSummary:
    date: date
    total_cost_cny: Decimal
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    unique_users: int


def utc_day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


async def record_llm_call(
    db: AsyncSession,
    *,
    task_id: uuid.UUID | str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_cny: float,
) -> None:
    try:
        try:
            tid = uuid.UUID(str(task_id))
        except (ValueError, TypeError):
            return
        result = await db.execute(select(Task).where(Task.id == tid))
        task = result.scalar_one_or_none()
        if task is None:
            logger.warning(
                "cost_monitor.record.skipped",
                task_id=str(task_id),
                reason="task not found",
            )
            return
        task.prompt_tokens = (task.prompt_tokens or 0) + int(prompt_tokens)
        task.completion_tokens = (task.completion_tokens or 0) + int(
            completion_tokens
        )
        new_cost = float(task.cost_cny or 0) + float(cost_cny)
        task.cost_cny = round(new_cost, 6)
        await db.flush()
    except Exception as exc:
        logger.error(
            "cost_monitor.record.failed",
            task_id=str(task_id),
            error=str(exc),
        )
        await db.rollback()


async def get_daily_cost(
    db: AsyncSession,
    day: date | None = None,
) -> DailyCostSummary:
    target = day or datetime.now(timezone.utc).date()
    start, end = utc_day_range(target)
    stmt = (
        select(
            func.coalesce(func.sum(Task.cost_cny), 0).label("total_cost"),
            func.count(Task.id).label("call_count"),
            func.coalesce(func.sum(Task.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(
                func.sum(Task.completion_tokens), 0
            ).label("completion_tokens"),
            func.count(func.distinct(Task.user_id)).label("unique_users"),
        )
        .where(
            and_(
                Task.created_at >= start,
                Task.created_at < end,
                Task.status != TaskStatus.PENDING,
            )
        )
    )
    result = await db.execute(stmt)
    row = result.one()
    return DailyCostSummary(
        date=target,
        total_cost_cny=Decimal(str(row.total_cost or 0)),
        call_count=int(row.call_count or 0),
        prompt_tokens=int(row.prompt_tokens or 0),
        completion_tokens=int(row.completion_tokens or 0),
        unique_users=int(row.unique_users or 0),
    )


async def check_daily_alert(
    db: AsyncSession,
    *,
    threshold_cny: float | None = None,
    day: date | None = None,
) -> bool:
    threshold = float(threshold_cny or settings.llm_daily_cost_limit_cny)
    summary = await get_daily_cost(db, day)
    if float(summary.total_cost_cny) > threshold:
        logger.warning(
            "cost_monitor.alert.exceeded",
            date=str(summary.date),
            cost_cny=float(summary.total_cost_cny),
            threshold_cny=threshold,
            call_count=summary.call_count,
            unique_users=summary.unique_users,
        )
        await notify_cost_alert(float(summary.total_cost_cny), threshold)
        return True
    return False


async def top_spenders(
    db: AsyncSession,
    *,
    day: date | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    target = day or datetime.now(timezone.utc).date()
    start, end = utc_day_range(target)
    stmt = (
        select(
            Task.user_id,
            func.coalesce(func.sum(Task.cost_cny), 0).label("total_cost"),
            func.count(Task.id).label("task_count"),
        )
        .where(
            and_(
                Task.created_at >= start,
                Task.created_at < end,
                Task.status != TaskStatus.PENDING,
            )
        )
        .group_by(Task.user_id)
        .order_by(func.sum(Task.cost_cny).desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [
        {
            "user_id": str(row.user_id),
            "total_cost_cny": float(row.total_cost or 0),
            "task_count": int(row.task_count or 0),
        }
        for row in result.all()
    ]


async def reset_alert_marker(db: AsyncSession) -> None:  # noqa: ARG001
    return None


__all__ = [
    "DailyCostSummary",
    "record_llm_call",
    "get_daily_cost",
    "check_daily_alert",
    "top_spenders",
    "reset_alert_marker",
]