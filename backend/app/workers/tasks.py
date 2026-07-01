from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.glossary import Glossary
from app.models.quota import Quota
from app.models.task import Task, TaskStatus
from app.services.cost_monitor_service import check_daily_alert
from app.services.glossary_service import build_glossary_prompt as _build_glossary_prompt
from app.services.markdown_service import (
    convert_pdf_to_docx,
    convert_pdf_to_markdown,
    extract_pages_text,
)
from app.services.storage_service import (
    build_download_prefix,
    build_object_key,
    get_storage,
)
from app.services.structure_service import (
    build_skip_references_prompt,
    detect_sections,
)
from app.workers.progress import publish_progress, store_progress_snapshot


settings = get_settings()
logger = get_logger(__name__)


_broker: RedisBroker | None = None


def get_broker() -> RedisBroker:
    global _broker
    if _broker is None:
        _broker = RedisBroker(url=settings.redis_url)
        dramatiq.set_broker(_broker)
    return _broker


def _safe_sentry_capture(exc: BaseException, **extra: Any) -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(exc)
    except Exception:
        return


async def _update_task(
    task_id: uuid.UUID,
    **fields: Any,
) -> None:
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Task).where(Task.id == task_id)
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()
            if task is None:
                return
            for key, value in fields.items():
                setattr(task, key, value)
            await session.commit()
        except Exception as exc:
            logger.error(
                "worker.update_task.failed",
                task_id=str(task_id),
                error=str(exc),
            )
            await session.rollback()


async def _load_glossaries(
    glossary_ids: list[uuid.UUID] | None,
    user_id: uuid.UUID,
) -> list[Glossary]:
    ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for gid in glossary_ids or []:
        if gid in seen:
            continue
        seen.add(gid)
        ids.append(gid)
    if not ids:
        return []
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Glossary).where(
                Glossary.id.in_(ids),
                Glossary.is_active.is_(True),
            )
            result = await session.execute(stmt)
            glossaries = list(result.scalars().all())
            visible: list[Glossary] = []
            for gloss in glossaries:
                if gloss.is_system:
                    visible.append(gloss)
                elif gloss.user_id == user_id:
                    visible.append(gloss)
            visible.sort(key=lambda g: ids.index(g.id))
            return visible
        except Exception as exc:
            logger.warning(
                "worker.load_glossary.failed",
                glossary_ids=[str(g) for g in ids],
                error=str(exc),
            )
            return []


async def _load_glossary_terms(
    glossary_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    if not glossary_id:
        return []
    glossaries = await _load_glossaries([glossary_id], user_id)
    if not glossaries:
        return []
    return list(glossaries[0].terms or [])


async def _consume_quota(
    user_id: uuid.UUID,
    pages: int,
) -> None:
    if pages <= 0:
        return
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Quota).where(Quota.user_id == user_id)
            result = await session.execute(stmt)
            quota = result.scalar_one_or_none()
            if quota is None:
                quota = Quota(user_id=user_id)
                session.add(quota)
                await session.flush()
            quota.used_pages = (quota.used_pages or 0) + pages
            quota.used_daily_pages = (quota.used_daily_pages or 0) + pages
            await session.commit()
        except Exception as exc:
            logger.error(
                "worker.consume_quota.failed",
                user_id=str(user_id),
                error=str(exc),
            )
            await session.rollback()


async def _publish(
    task_id: uuid.UUID,
    progress: int,
    *,
    status: str | None = None,
    message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        await publish_progress(
            task_id,
            progress,
            status=status,
            message=message,
            extra=extra,
        )
        snapshot = {
            "task_id": str(task_id),
            "progress": progress,
            "status": status,
            "message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            snapshot.update(extra)
        await store_progress_snapshot(task_id, snapshot)
    except Exception:
        pass


def _detect_pdf2zh_cli() -> str | None:
    """Detect the pdf2zh_next CLI (not Python API — for use with subprocess)."""
    scripts_dir = Path(sys.executable).parent
    candidates = [
        str(scripts_dir / "pdf2zh_next"),
        str(scripts_dir / "pdf2zh_next.exe"),
        str(scripts_dir / "pdf2zh"),
        str(scripts_dir / "pdf2zh.exe"),
        "pdf2zh_next",
        "pdf2zh",
    ]
    for candidate in candidates:
        try:
            subprocess.run(
                [candidate, "--help"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None


def _translate_with_pdf2zh(
    pdf_path: str,
    output_dir: str,
    *,
    source_lang: str,
    target_lang: str,
    service: str,
    model: str,
    api_key: str,
    base_url: str,
    custom_prompt: str,
    progress_hook=None,
) -> dict[str, Any]:
    backend = _detect_pdf2zh_cli()
    if backend is None:
        raise RuntimeError("pdf2zh_next CLI not available; ensure pdf2zh_next is installed in the venv")
    cmd = [
        backend,
        str(pdf_path),
        "--output",
        output_dir,
        "--lang-in",
        source_lang,
        "--lang-out",
        target_lang,
        "--custom-system-prompt",
        custom_prompt,
    ]
    service_lower = (service or "").lower()
    if service_lower == "deepseek":
        cmd.extend(["--enabled-services", "deepseek"])
        if api_key:
            cmd.extend(["--deepseek-api-key", api_key])
        if model:
            cmd.extend(["--deepseek-model", model])
    elif service_lower == "glm" or service_lower == "zhipu":
        cmd.extend(["--enabled-services", "zhipu"])
        if api_key:
            cmd.extend(["--zhipu-api-key", api_key])
        if model:
            cmd.extend(["--zhipu-model", model])
    elif service_lower == "openai":
        cmd.extend(["--enabled-services", "openai"])
        if api_key:
            cmd.extend(["--openai-api-key", api_key])
        if base_url:
            cmd.extend(["--openai-base-url", base_url])
        if model:
            cmd.extend(["--openai-model", model])
    else:
        cmd.extend(["--enabled-services", service_lower or "openai"])
        if api_key:
            cmd.extend(["--openai-api-key", api_key])
        if base_url:
            cmd.extend(["--openai-base-url", base_url])
        if model:
            cmd.extend(["--openai-model", model])
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=3600,
        env={**os.environ, "PATH": os.environ["PATH"]},
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pdf2zh CLI failed: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return {"ok": True}


def _resolve_llm_config(task: Task) -> dict[str, str]:
    from app.services.llm_service import get_llm_config

    try:
        cfg = get_llm_config(task.llm_service)
    except Exception:
        cfg = get_llm_config(settings.llm_default_service)
    if not cfg.get("api_key"):
        cfg = get_llm_config(settings.llm_default_service)
    return cfg


def _build_custom_prompt(
    task: Task,
    glossaries: list[Glossary],
    skip_refs: bool,
) -> str:
    parts: list[str] = []
    glossary_block = _build_glossary_prompt(glossaries)
    if glossary_block:
        parts.append(glossary_block)
    skip_block = build_skip_references_prompt(skip_refs)
    if skip_block:
        parts.append(skip_block)
    parts.append(
        "Translate the following academic paper excerpt from "
        f"{task.source_language} to {task.target_language}. "
        "Preserve mathematical notation, citations, and figure references."
    )
    return "\n\n".join(parts)


async def _run_translation_inner(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        tid = uuid.UUID(task_id)
    except (ValueError, TypeError) as exc:
        logger.error("worker.translation.invalid_task_id", task_id=task_id, error=str(exc))
        return {"task_id": task_id, "status": "failed", "error": str(exc)}

    main_loop = asyncio.get_running_loop()

    async with AsyncSessionLocal() as session:
        stmt = select(Task).where(Task.id == tid)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            logger.error("worker.translation.task_not_found", task_id=task_id)
            return {"task_id": task_id, "status": "failed", "error": "task not found"}
        if task.status == TaskStatus.CANCELLED:
            logger.info("worker.translation.skipped_cancelled", task_id=task_id)
            return {"task_id": task_id, "status": "cancelled"}
        task.status = TaskStatus.PROCESSING
        task.progress = 5
        task.started_at = datetime.now(timezone.utc)
        await session.commit()

    await _publish(tid, 5, status="processing", message="task started")

    tmp_dir = Path(tempfile.mkdtemp(prefix="paper-translate-", dir=settings.upload_tmp_dir))
    source_key = build_object_key(
        uuid.UUID(str(task.user_id)),
        tid,
        task.filename,
        prefix="uploads",
    )
    local_pdf_path = tmp_dir / task.filename

    try:
        storage = get_storage()
        blob = await storage.get_object(source_key)
        if not blob:
            existing = task.source_url
            if existing and existing != source_key:
                blob = await storage.get_object(existing)
        if not blob:
            raise RuntimeError(f"source pdf not found in storage: {source_key}")
        local_pdf_path.write_bytes(blob)
        await _publish(tid, 15, status="processing", message="source downloaded")

        glossary_ids: list[uuid.UUID] = []
        if isinstance(payload, dict):
            extra_ids = payload.get("glossary_ids") or payload.get("glossaries") or []
            if isinstance(extra_ids, list):
                for raw_id in extra_ids:
                    try:
                        glossary_ids.append(uuid.UUID(str(raw_id)))
                    except (ValueError, TypeError):
                        continue
            primary_id = payload.get("glossary_id")
            if primary_id:
                try:
                    glossary_ids.append(uuid.UUID(str(primary_id)))
                except (ValueError, TypeError):
                    pass
        if task.glossary_id:
            glossary_ids.append(task.glossary_id)

        glossaries = await _load_glossaries(
            glossary_ids,
            uuid.UUID(str(task.user_id)),
        )
        try:
            pages = await extract_pages_text(local_pdf_path)
        except Exception as exc:
            logger.warning("worker.extract.failed", error=str(exc))
            pages = []
        full_text = "\n".join(p.get("text", "") for p in pages)
        sections = await detect_sections(full_text, use_llm=True)
        await _publish(tid, 25, status="processing", message="sections detected")

        skip_refs = bool(task.options.get("skip_references", True)) if isinstance(task.options, dict) else True
        custom_prompt = _build_custom_prompt(task, glossaries, skip_refs)
        cfg = _resolve_llm_config(task)
        output_dir = tmp_dir / "out"
        output_dir.mkdir(parents=True, exist_ok=True)

        progress_state = {"value": 25}

        def _hook(percent: float) -> None:
            try:
                pct = max(progress_state["value"], min(95, int(percent)))
            except Exception:
                return
            if pct - progress_state["value"] >= 5:
                progress_state["value"] = pct
                try:
                    asyncio.run_coroutine_threadsafe(
                        _publish(tid, pct, status="processing", message="translating"),
                        main_loop,
                    )
                except Exception:
                    return

        def _sync_translate() -> dict[str, Any]:
            return _translate_with_pdf2zh(
                str(local_pdf_path),
                str(output_dir),
                source_lang=task.source_language,
                target_lang=task.target_language,
                service=task.llm_service,
                model=cfg["model"],
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                custom_prompt=custom_prompt,
                progress_hook=_hook,
            )

        import threading

        heartbeat_stop = threading.Event()
        heartbeat_error: dict[str, BaseException] = {}

        def _heartbeat_loop() -> None:
            """Emit periodic progress while the CLI runs.

            pdf2zh_next does not call our progress hook, so without this
            thread the UI sits at the same percentage for the entire
            translation duration. We tick 30→90 in ~5% steps every 8s.
            We also write the value to the DB so REST polling shows it.
            """
            import time as _time

            next_pct = 30
            while not heartbeat_stop.is_set():
                if heartbeat_stop.wait(8.0):
                    break
                if next_pct > 90:
                    continue
                pct = next_pct
                next_pct += 5
                if pct <= progress_state["value"]:
                    continue
                progress_state["value"] = pct
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        _publish(tid, pct, status="processing", message="translating"),
                        main_loop,
                    )
                    future.result(timeout=5)
                except BaseException as exc:  # noqa: BLE001
                    heartbeat_error["exc"] = exc
                    return
                # Mirror to DB so REST polling reflects progress
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        _update_task(tid, progress=pct),
                        main_loop,
                    )
                    future.result(timeout=5)
                except BaseException:  # noqa: BLE001
                    pass

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop, name=f"pt-heartbeat-{tid}", daemon=True
        )
        heartbeat_thread.start()

        try:
            translate_result = await asyncio.to_thread(_sync_translate)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
        await _publish(tid, 60, status="processing", message="translation finished")

        result_pdf_candidates = sorted(
            output_dir.glob("*.pdf"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not result_pdf_candidates:
            result_pdf_candidates = sorted(
                tmp_dir.glob("*.pdf"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        if not result_pdf_candidates:
            raise RuntimeError("pdf2zh did not produce a translated PDF")

        # pdf2zh 输出 <stem>.<lang>.dual.pdf 和 <stem>.<lang>.mono.pdf
        # 按 stem + lang-in + lang-out 区分;若命名不匹配则按 mtime 兜底。
        def _pick(suffix: str) -> Path | None:
            for p in result_pdf_candidates:
                if p.stem.endswith(f".{suffix}"):
                    return p
            return None

        dual_pdf_path = _pick("dual") or result_pdf_candidates[0]
        mono_pdf_path = _pick("mono")
        if mono_pdf_path is dual_pdf_path:
            mono_pdf_path = None  # 防止单文件版本时双指针

        download_prefix = build_download_prefix(
            uuid.UUID(str(task.user_id)),
            tid,
        )
        result_dual_key = f"{download_prefix}/translated-dual.pdf"
        await storage.put_object(
            result_dual_key,
            dual_pdf_path.read_bytes(),
            content_type="application/pdf",
        )
        result_url = await storage.generate_signed_url(result_dual_key)
        await _publish(tid, 75, status="processing", message="dual pdf uploaded")

        result_mono_url: str | None = None
        if mono_pdf_path is not None and mono_pdf_path.exists():
            result_mono_key = f"{download_prefix}/translated-mono.pdf"
            await storage.put_object(
                result_mono_key,
                mono_pdf_path.read_bytes(),
                content_type="application/pdf",
            )
            result_mono_url = await storage.generate_signed_url(result_mono_key)
            await _publish(tid, 78, status="processing", message="mono pdf uploaded")

        result_md_key = f"{download_prefix}/translated.md"
        result_docx_key = f"{download_prefix}/translated.docx"
        # HIDDEN-FEATURE: md/docx 暂时禁用,因为生成质量不达标(详见 HIDDEN_FEATURES.md)
        result_md_url: str | None = None
        result_docx_url: str | None = None
        if settings.enable_markdown_export:
            md_text = await convert_pdf_to_markdown(dual_pdf_path)
            await storage.put_object(
                result_md_key,
                md_text.encode("utf-8"),
                content_type="text/markdown; charset=utf-8",
            )
            result_md_url = await storage.generate_signed_url(result_md_key)
            await _publish(tid, 88, status="processing", message="markdown generated")
        else:
            await _publish(tid, 88, status="processing", message="markdown skipped (disabled)")

        if settings.enable_docx_export:
            docx_bytes = await convert_pdf_to_docx(dual_pdf_path)
            await storage.put_object(
                result_docx_key,
                docx_bytes,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            result_docx_url = await storage.generate_signed_url(result_docx_key)
            await _publish(tid, 96, status="processing", message="docx generated")
        else:
            await _publish(tid, 96, status="processing", message="docx skipped (disabled)")

        cost_cny = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        if isinstance(translate_result, dict):
            cost_cny = float(translate_result.get("cost_cny", 0) or 0)
            prompt_tokens = int(translate_result.get("prompt_tokens", 0) or 0)
            completion_tokens = int(translate_result.get("completion_tokens", 0) or 0)

        async with AsyncSessionLocal() as session:
            stmt = select(Task).where(Task.id == tid)
            result = await session.execute(stmt)
            t = result.scalar_one_or_none()
            if t is not None:
                t.status = TaskStatus.COMPLETED
                t.progress = 100
                t.result_url = result_url
                t.result_mono_url = result_mono_url
                t.result_md_url = result_md_url
                t.result_docx_url = result_docx_url
                t.source_url = source_key
                t.cost_cny = round(float(t.cost_cny or 0) + cost_cny, 6)
                t.prompt_tokens = (t.prompt_tokens or 0) + prompt_tokens
                t.completion_tokens = (t.completion_tokens or 0) + completion_tokens
                t.completed_at = datetime.now(timezone.utc)
                await session.commit()

        pages_consumed = max(1, task.page_count or 1)
        await _consume_quota(uuid.UUID(str(task.user_id)), pages_consumed)

        await _publish(
            tid,
            100,
            status="completed",
            message="done",
            extra={
                "result_url": result_url,
                "result_md_url": result_md_url,
                "result_docx_url": result_docx_url,
                "cost_cny": round(cost_cny, 6),
            },
        )
        try:
            async with AsyncSessionLocal() as session:
                await check_daily_alert(session)
        except Exception as exc:
            logger.warning("worker.cost_alert.failed", error=str(exc))

        return {
            "task_id": task_id,
            "status": "completed",
            "result_url": result_url,
            "cost_cny": cost_cny,
        }
    except Exception as exc:
        logger.exception(
            "worker.translation.failed",
            task_id=task_id,
            error=str(exc),
        )
        _safe_sentry_capture(exc, task_id=task_id)
        await _update_task(
            tid,
            status=TaskStatus.FAILED,
            error_message=str(exc),
            completed_at=datetime.now(timezone.utc),
        )
        await _publish(
            tid,
            100,
            status="failed",
            message=str(exc),
        )
        return {"task_id": task_id, "status": "failed", "error": str(exc)}
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


@dramatiq.actor(
    actor_name="process_translation_task",
    queue_name="translation",
    max_retries=3,
    min_backoff=5_000,
    max_backoff=60_000,
    time_limit=30 * 60_000,
)
def process_translation_task(task_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    logger.info("worker.translation.started", task_id=task_id, payload=payload or {})
    try:
        return asyncio.run(_run_translation_inner(task_id, payload or {}))
    except Exception as exc:
        logger.exception(
            "worker.translation.unhandled",
            task_id=task_id,
            error=str(exc),
        )
        _safe_sentry_capture(exc, task_id=task_id)
        return {"task_id": task_id, "status": "failed", "error": str(exc)}


@dramatiq.actor(
    actor_name="send_cost_alert",
    queue_name="notifications",
    max_retries=5,
    min_backoff=2_000,
)
def send_cost_alert(current_cost_cny: float, threshold_cny: float) -> bool:
    logger.warning(
        "worker.cost_alert",
        current_cost_cny=current_cost_cny,
        threshold_cny=threshold_cny,
    )
    from app.services.notification_service import notify_cost_alert as _notify

    try:
        return asyncio.run(_notify(current_cost_cny, threshold_cny))
    except Exception as exc:
        logger.error("worker.cost_alert.failed", error=str(exc))
        return False


@dramatiq.actor(
    actor_name="cleanup_expired_tasks",
    queue_name="maintenance",
    max_retries=1,
)
def cleanup_expired_tasks(batch_size: int = 100) -> int:
    async def _run() -> int:
        from app.services.task_service import cleanup_expired_tasks as _cleanup

        async with AsyncSessionLocal() as session:
            return await _cleanup(session, limit=batch_size)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("worker.cleanup.failed", error=str(exc))
        return 0


@dramatiq.actor(
    actor_name="reset_monthly_quotas",
    queue_name="maintenance",
    max_retries=1,
)
def reset_monthly_quotas() -> int:
    async def _run() -> int:
        from app.services.task_service import reset_monthly_quotas as _reset

        async with AsyncSessionLocal() as session:
            return await _reset(session)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("worker.reset_quotas.failed", error=str(exc))
        return 0


@dramatiq.actor(
    actor_name="check_daily_alert",
    queue_name="notifications",
    max_retries=3,
)
def check_daily_alert_actor(threshold_cny: float | None = None) -> bool:
    async def _run() -> bool:
        async with AsyncSessionLocal() as session:
            return await check_daily_alert(session, threshold_cny=threshold_cny)

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("worker.daily_alert.failed", error=str(exc))
        return False


def enqueue_translation(task_id: uuid.UUID, payload: dict[str, Any] | None = None) -> str:
    get_broker()
    message = process_translation_task.send(str(task_id), payload or {})
    return str(message.message_id)


def enqueue_cost_alert(current_cost_cny: float, threshold_cny: float) -> str:
    get_broker()
    message = send_cost_alert.send(current_cost_cny, threshold_cny)
    return str(message.message_id)


def enqueue_cleanup(batch_size: int = 100) -> str:
    get_broker()
    message = cleanup_expired_tasks.send(batch_size)
    return str(message.message_id)


def enqueue_reset_quotas() -> str:
    get_broker()
    message = reset_monthly_quotas.send()
    return str(message.message_id)


def enqueue_daily_alert_check(threshold_cny: float | None = None) -> str:
    get_broker()
    message = check_daily_alert_actor.send(threshold_cny)
    return str(message.message_id)


__all__ = [
    "process_translation_task",
    "send_cost_alert",
    "cleanup_expired_tasks",
    "reset_monthly_quotas",
    "check_daily_alert_actor",
    "enqueue_translation",
    "enqueue_cost_alert",
    "enqueue_cleanup",
    "enqueue_reset_quotas",
    "enqueue_daily_alert_check",
    "get_broker",
]