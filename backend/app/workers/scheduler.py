from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.cost_monitor_service import check_daily_alert
from app.services.task_service import (
    cleanup_expired_tasks as _cleanup_expired_tasks,
)
from app.services.task_service import (
    reset_monthly_quotas as _reset_monthly_quotas,
)


settings = get_settings()
logger = get_logger(__name__)


_scheduler_lock = threading.Lock()
_scheduler_state: dict[str, Any] = {
    "started": False,
    "stopped": False,
    "scheduler": None,
}


def _try_import_apscheduler():
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: F401
        from apscheduler.triggers.cron import CronTrigger  # noqa: F401

        return True
    except ImportError:
        return False


async def cleanup_expired_tasks_job(batch_size: int = 100) -> int:
    async with AsyncSessionLocal() as session:
        try:
            count = await _cleanup_expired_tasks(session, limit=batch_size)
            logger.info(
                "scheduler.cleanup_expired_tasks",
                count=count,
            )
            return count
        except Exception as exc:
            logger.error(
                "scheduler.cleanup_expired_tasks.failed",
                error=str(exc),
            )
            return 0


async def reset_monthly_quotas_job() -> int:
    async with AsyncSessionLocal() as session:
        try:
            count = await _reset_monthly_quotas(session)
            logger.info(
                "scheduler.reset_monthly_quotas",
                count=count,
            )
            return count
        except Exception as exc:
            logger.error(
                "scheduler.reset_monthly_quotas.failed",
                error=str(exc),
            )
            return 0


async def check_daily_alert_job() -> bool:
    async with AsyncSessionLocal() as session:
        try:
            triggered = await check_daily_alert(session)
            logger.info(
                "scheduler.check_daily_alert",
                triggered=triggered,
                now=datetime.now(timezone.utc).isoformat(),
            )
            return triggered
        except Exception as exc:
            logger.error(
                "scheduler.check_daily_alert.failed",
                error=str(exc),
            )
            return False


async def run_loop(
    *,
    cleanup_interval_minutes: int = 60,
    daily_check_hour: int = 0,
    daily_check_minute: int = 5,
) -> None:
    last_cleanup: datetime | None = None
    last_daily_check: datetime | None = None
    last_monthly_reset: datetime | None = None
    logger.info(
        "scheduler.run_loop.started",
        cleanup_interval_minutes=cleanup_interval_minutes,
    )
    while not _scheduler_state["stopped"]:
        try:
            now = datetime.now(timezone.utc)
            if (
                last_cleanup is None
                or (now - last_cleanup).total_seconds() >= cleanup_interval_minutes * 60
            ):
                await cleanup_expired_tasks_job()
                last_cleanup = now
            if (
                last_daily_check is None
                or (
                    now.date() != last_daily_check.date()
                    and now.hour >= daily_check_hour
                    and now.minute >= daily_check_minute
                )
            ):
                await check_daily_alert_job()
                last_daily_check = now
            if (
                last_monthly_reset is None
                or now.day == 1
                and now.date() != last_monthly_reset.date()
                and now.hour == 0
                and now.minute < 5
            ):
                await reset_monthly_quotas_job()
                last_monthly_reset = now
        except Exception as exc:
            logger.error(
                "scheduler.loop_iteration.failed",
                error=str(exc),
            )
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break


def start_scheduler(*, background: bool = True) -> Any:
    with _scheduler_lock:
        if _scheduler_state["started"]:
            return _scheduler_state["scheduler"]
        if _try_import_apscheduler():
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger

            scheduler = AsyncIOScheduler(timezone="UTC")
            scheduler.add_job(
                cleanup_expired_tasks_job,
                trigger=IntervalTrigger(minutes=60),
                id="cleanup_expired_tasks",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            scheduler.add_job(
                check_daily_alert_job,
                trigger=CronTrigger(hour=0, minute=5),
                id="daily_cost_alert",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            scheduler.add_job(
                reset_monthly_quotas_job,
                trigger=CronTrigger(day=1, hour=0, minute=0),
                id="reset_monthly_quotas",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            if background:
                scheduler.start()
            _scheduler_state["scheduler"] = scheduler
            _scheduler_state["started"] = True
            logger.info("scheduler.started", backend="apscheduler")
            return scheduler
        if background:
            thread = threading.Thread(
                target=_run_fallback_thread,
                daemon=True,
                name="paper-translate-scheduler",
            )
            thread.start()
            _scheduler_state["thread"] = thread
            _scheduler_state["started"] = True
            logger.info("scheduler.started", backend="asyncio-loop-thread")
            return None
        return None


def _run_fallback_thread() -> None:
    try:
        asyncio.run(run_loop())
    except Exception as exc:
        logger.error("scheduler.fallback_thread.failed", error=str(exc))


def stop_scheduler() -> None:
    with _scheduler_lock:
        _scheduler_state["stopped"] = True
        scheduler = _scheduler_state.get("scheduler")
        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                pass
            _scheduler_state["scheduler"] = None
        _scheduler_state["started"] = False
        logger.info("scheduler.stopped")


__all__ = [
    "start_scheduler",
    "stop_scheduler",
    "cleanup_expired_tasks_job",
    "reset_monthly_quotas_job",
    "check_daily_alert_job",
]