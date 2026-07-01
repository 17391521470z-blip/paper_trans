from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.quota import Quota
from app.models.task import Task, TaskStatus
from app.models.user import User


settings = get_settings()
logger = get_logger(__name__)


PDF_MAGIC: Final[bytes] = b"%PDF-"
PDF_MAX_BYTES: Final[int] = settings.upload_max_size
PDF_MAX_PAGES: Final[int] = settings.upload_max_pages


@dataclass(slots=True)
class PDFValidation:
    is_valid: bool
    page_count: int
    size_bytes: int
    error: str | None = None


def compute_pdf_hash(blob: bytes) -> str:
    if not blob:
        raise ValueError("cannot hash empty blob")
    return hashlib.sha256(blob).hexdigest()


def compute_pdf_hash_streaming(fileobj: io.BufferedIOBase, chunk_size: int = 1024 * 1024) -> str:
    sha = hashlib.sha256()
    while True:
        chunk = fileobj.read(chunk_size)
        if not chunk:
            break
        sha.update(chunk)
    return sha.hexdigest()


def compute_pdf_hash_from_path(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {path}")
    with p.open("rb") as f:
        return compute_pdf_hash_streaming(f)


def _count_pdf_pages_via_header(blob: bytes) -> int | None:
    try:
        head = blob[: 1024 * 1024].decode("latin-1", errors="ignore")
    except Exception:
        return None
    marker = "/Type /Page"
    count = head.count(marker)
    if count == 0:
        marker_alt = "/Type/Page"
        count = head.count(marker_alt)
    return count or None


def _count_pdf_pages_via_trailer(blob: bytes) -> int | None:
    tail = blob[-1024 * 256 :].decode("latin-1", errors="ignore")
    if "/Count" not in tail:
        return None
    for token in tail.split("/Count"):
        if not token:
            continue
        snippet = token.lstrip().split()
        if not snippet:
            continue
        try:
            return int(snippet[0])
        except ValueError:
            continue
    return None


def _estimate_page_count(blob: bytes) -> int:
    trailer_count = _count_pdf_pages_via_trailer(blob)
    if trailer_count:
        return trailer_count
    header_count = _count_pdf_pages_via_header(blob)
    if header_count:
        return header_count
    return 0


def validate_pdf(
    blob: bytes,
    *,
    max_size: int = PDF_MAX_BYTES,
    max_pages: int = PDF_MAX_PAGES,
) -> PDFValidation:
    size = len(blob)
    if size == 0:
        return PDFValidation(False, 0, 0, "empty file")
    if size > max_size:
        return PDFValidation(
            False,
            0,
            size,
            f"file too large: {size} > {max_size} bytes",
        )
    if not blob.startswith(PDF_MAGIC):
        return PDFValidation(False, 0, size, "missing %PDF- magic header")
    if not blob.rstrip().endswith(b"%%EOF"):
        return PDFValidation(False, 0, size, "missing %%EOF trailer")
    page_count = _estimate_page_count(blob)
    if page_count and page_count > max_pages:
        return PDFValidation(
            False,
            page_count,
            size,
            f"page count {page_count} exceeds limit {max_pages}",
        )
    return PDFValidation(True, page_count, size, None)


def build_object_key(user_id: uuid.UUID, filename: str, file_hash: str) -> str:
    safe_name = Path(str(filename)).name.replace(" ", "_")
    return f"uploads/{user_id}/{str(file_hash)[:12]}/{safe_name}"


def build_result_key(user_id: uuid.UUID, task_id: uuid.UUID, suffix: str) -> str:
    return f"results/{user_id}/{task_id}/{suffix}"


def ensure_upload_tmp_dir() -> Path:
    p = Path(settings.upload_tmp_dir)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        import tempfile

        p = Path(tempfile.gettempdir()) / "paper-translate" / "uploads"
        p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(slots=True)
class EnqueueResult:
    task: Task
    cached: bool = False


async def _find_completed_cached_task(
    db: AsyncSession,
    file_hash: str,
    user_id: uuid.UUID,
) -> Task | None:
    if not file_hash:
        return None
    stmt = (
        select(Task)
        .where(
            and_(
                Task.file_hash == file_hash,
                Task.user_id == user_id,
                Task.status == TaskStatus.COMPLETED,
            )
        )
        .order_by(Task.completed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def enqueue_translation_task(
    db: AsyncSession,
    user: User,
    file_bytes: bytes,
    filename: str,
    options: dict[str, Any],
) -> EnqueueResult:
    if not file_bytes:
        raise ValueError("file_bytes is empty")
    if not filename:
        raise ValueError("filename is required")
    file_hash = options.get("file_hash") or compute_pdf_hash(file_bytes)
    cached_task = await _find_completed_cached_task(db, file_hash, user.id)
    if cached_task is not None:
        logger.info(
            "task_service.cache_hit",
            user_id=str(user.id),
            task_id=str(cached_task.id),
            file_hash=file_hash,
        )
        return EnqueueResult(task=cached_task, cached=True)
    validation = validate_pdf(file_bytes)
    if not validation.is_valid:
        raise ValueError(validation.error or "invalid pdf")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)
    task = Task(
        user_id=user.id,
        filename=filename,
        file_hash=file_hash,
        file_size=validation.size_bytes,
        page_count=validation.page_count,
        status=TaskStatus.PENDING,
        progress=0,
        options=options.get("options") or {},
        source_language=options.get("source_language", "en"),
        target_language=options.get("target_language", "zh"),
        llm_service=options.get("llm_service", settings.llm_default_service),
        glossary_id=options.get("glossary_id"),
        source_url=None,
        expires_at=expires_at,
    )
    db.add(task)
    await db.flush()
    return EnqueueResult(task=task, cached=False)


async def get_task_for_user(
    db: AsyncSession,
    user: User,
    task_id: uuid.UUID | str,
) -> Task | None:
    try:
        tid = uuid.UUID(str(task_id))
    except (ValueError, TypeError):
        return None
    stmt = select(Task).where(and_(Task.id == tid, Task.user_id == user.id))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def cancel_task(
    db: AsyncSession,
    user: User,
    task_id: uuid.UUID | str,
) -> bool:
    task = await get_task_for_user(db, user, task_id)
    if task is None:
        return False
    if task.status not in {TaskStatus.PENDING, TaskStatus.PROCESSING}:
        return False
    task.status = TaskStatus.CANCELLED
    task.completed_at = datetime.now(timezone.utc)
    task.error_message = "cancelled by user"
    await db.flush()
    return True


async def list_user_tasks(
    db: AsyncSession,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
) -> list[Task]:
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    offset = (page - 1) * page_size
    stmt = (
        select(Task)
        .where(Task.user_id == user.id)
        .order_by(Task.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_user_tasks(db: AsyncSession, user: User) -> int:
    from sqlalchemy import func

    stmt = select(func.count(Task.id)).where(Task.user_id == user.id)
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def cleanup_expired_tasks(
    db: AsyncSession,
    *,
    storage: Any | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    from app.services.storage_service import get_storage

    cutoff = now or datetime.now(timezone.utc)
    stmt = (
        select(Task)
        .where(Task.expires_at.is_not(None))
        .where(Task.expires_at < cutoff)
        .where(
            Task.status.in_(
                [
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ]
            )
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())
    if not tasks:
        return 0
    backend = storage or get_storage()
    keys_to_delete: list[str] = []
    for task in tasks:
        if task.source_url and task.source_url.startswith("uploads/"):
            keys_to_delete.append(task.source_url)
        if task.result_url and task.result_url.startswith("downloads/"):
            keys_to_delete.append(task.result_url)
        if task.result_mono_url and task.result_mono_url.startswith("downloads/"):
            keys_to_delete.append(task.result_mono_url)
        if task.result_md_url and task.result_md_url.startswith("downloads/"):
            keys_to_delete.append(task.result_md_url)
        if task.result_docx_url and task.result_docx_url.startswith("downloads/"):
            keys_to_delete.append(task.result_docx_url)
    for key in keys_to_delete:
        try:
            await backend.delete(key)
        except Exception as exc:
            logger.warning(
                "task_service.cleanup.delete_failed",
                key=key,
                error=str(exc),
            )
    task_ids = [task.id for task in tasks]
    delete_stmt = update(Task).where(Task.id.in_(task_ids)).values(
        status=TaskStatus.CANCELLED,
        error_message="expired",
        result_url=None,
        result_mono_url=None,
        result_md_url=None,
        result_docx_url=None,
        source_url=None,
    )
    await db.execute(delete_stmt)
    await db.flush()
    logger.info(
        "task_service.cleanup.completed",
        count=len(tasks),
    )
    return len(tasks)


async def reset_monthly_quotas(db: AsyncSession, *, now: datetime | None = None) -> int:
    today = (now or datetime.now(timezone.utc)).date()
    if today.month == 12:
        next_reset = datetime(today.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_reset = datetime(today.year, today.month + 1, 1, tzinfo=timezone.utc)
    daily_reset = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    stmt = (
        update(Quota)
        .values(
            used_pages=0,
            used_daily_pages=0,
            reset_at=next_reset,
            daily_reset_at=daily_reset,
        )
    )
    result = await db.execute(stmt)
    await db.flush()
    return int(result.rowcount or 0)


async def reap_stale_processing_tasks(
    db: AsyncSession,
    *,
    older_than_seconds: int = 600,
    now: datetime | None = None,
) -> int:
    """Mark PROCESSING tasks whose worker disappeared as FAILED.

    Used at app startup to recover from crash-killed workers. A task is
    considered stale if it has been in PROCESSING state for longer than
    `older_than_seconds` without updating `updated_at` or `progress`.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=older_than_seconds)
    stmt = (
        update(Task)
        .where(
            Task.status == TaskStatus.PROCESSING,
            Task.started_at.is_not(None),
            Task.started_at < cutoff,
        )
        .values(
            status=TaskStatus.FAILED,
            error_message="worker process terminated; recovered on startup",
            completed_at=datetime.now(timezone.utc),
        )
    )
    result = await db.execute(stmt)
    await db.flush()
    return int(result.rowcount or 0)


__all__ = [
    "PDFValidation",
    "compute_pdf_hash",
    "compute_pdf_hash_streaming",
    "compute_pdf_hash_from_path",
    "validate_pdf",
    "build_object_key",
    "build_result_key",
    "ensure_upload_tmp_dir",
    "EnqueueResult",
    "enqueue_translation_task",
    "get_task_for_user",
    "cancel_task",
    "list_user_tasks",
    "count_user_tasks",
    "cleanup_expired_tasks",
    "reap_stale_processing_tasks",
    "reset_monthly_quotas",
]