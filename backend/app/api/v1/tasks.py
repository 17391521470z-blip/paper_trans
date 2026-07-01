from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    DbSession,
    _load_quota,
    get_current_active_user,
    get_current_user_from_token,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services import task_service
from app.services.storage_service import build_object_key as storage_build_object_key, get_storage
from app.services.quota_service import consume_quota
from app.workers.progress import (
    get_progress_snapshot,
    publish_progress,
    subscribe_progress,
)
from app.workers.tasks import enqueue_translation, get_broker


settings = get_settings()
logger = get_logger(__name__)


router: APIRouter = APIRouter()


class TaskCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    status: Literal["pending", "processing", "completed", "failed", "cancelled", "cached"]
    cached: bool = False
    cached_from: str | None = None
    filename: str
    file_size: int = 0
    page_count: int = 0
    expires_at: datetime | None = None


class TaskListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="上传 PDF 并提交翻译任务",
)
async def create_task(
    db: DbSession,
    user: User = Depends(get_current_active_user),
    file: UploadFile = File(..., description="PDF file"),
    source_language: str = Form(default="en"),
    target_language: str = Form(default="zh"),
    llm_service: Literal["deepseek", "glm", "openai"] = Form(default="deepseek"),
    glossary_id: str | None = Form(default=None),
    skip_references: bool = Form(default=True),
    detect_sections: bool = Form(default=True),
    output_formats: str = Form(default="pdf"),
    options: str | None = Form(default=None),
) -> TaskCreateResponse:
    quota = await _load_quota(db, user.id)
    check = consume_quota(
        user_id=user.id,
        used_pages=quota.used_pages,
        used_daily_pages=quota.used_daily_pages,
        requested_pages=1,
    )
    if not check.consumed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "quota_exceeded",
                "reason": check.reason,
                "remaining_monthly": max(quota.monthly_pages - quota.used_pages, 0),
                "remaining_daily": max(quota.daily_pages - quota.used_daily_pages, 0),
            },
        )

    if file.content_type and file.content_type not in (
        "application/pdf",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "invalid_mime",
                "expected": "application/pdf",
                "received": file.content_type,
            },
        )

    blob = await file.read()
    if not blob:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_file"},
        )
    if len(blob) > settings.upload_max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "file_too_large",
                "max_bytes": settings.upload_max_size,
                "received_bytes": len(blob),
            },
        )

    validation = task_service.validate_pdf(blob)
    if not validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_pdf",
                "error": validation.error,
            },
        )

    try:
        parsed_options: dict[str, Any] = {}
        if options:
            try:
                parsed_options = json.loads(options)
                if not isinstance(parsed_options, dict):
                    parsed_options = {}
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "invalid_options", "error": "options must be JSON object"},
                )
        glossary_uuid: uuid.UUID | None = None
        if glossary_id:
            try:
                glossary_uuid = uuid.UUID(glossary_id)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "invalid_glossary_id"},
                )

        formats_list = [f.strip() for f in output_formats.split(",") if f.strip()]
        if not formats_list:
            formats_list = ["pdf"]

        merged_options = {
            "source_language": source_language,
            "target_language": target_language,
            "llm_service": llm_service,
            "glossary_id": str(glossary_uuid) if glossary_uuid else None,
            "skip_references": skip_references,
            "detect_sections": detect_sections,
            "output_formats": formats_list,
            "options": parsed_options,
        }

        enqueue_result = await task_service.enqueue_translation_task(
            db,
            user,
            blob,
            file.filename or "untitled.pdf",
            merged_options,
        )
        task = enqueue_result.task
        if enqueue_result.cached:
            return TaskCreateResponse(
                task_id=str(task.id),
                status="completed",
                cached=True,
                cached_from=str(task.id),
                filename=task.filename,
                file_size=task.file_size,
                page_count=task.page_count,
                expires_at=task.expires_at,
            )

        storage = get_storage()
        upload_key = storage_build_object_key(
            user.id,
            task.id,
            file.filename or "untitled.pdf",
            prefix="uploads",
        )
        if not upload_key.startswith("uploads/"):
            upload_key = f"uploads/{user.id}/{task.id}/{file.filename or 'untitled.pdf'}"
        await storage.put_object(
            upload_key,
            blob,
            content_type="application/pdf",
        )
        task.source_url = upload_key
        task.dramatiq_message_id = None
        await db.commit()
        await db.refresh(task)

        try:
            get_broker()
            message_id = enqueue_translation(task.id, {"upload_key": upload_key})
            task.dramatiq_message_id = message_id
            await db.commit()
            logger.info("tasks.enqueued", task_id=str(task.id), backend="dramatiq")
        except Exception as exc:
            logger.warning(
                "tasks.enqueue.failed_fallback_direct",
                task_id=str(task.id),
                error=str(exc),
            )
            from app.workers.tasks import _run_translation_inner

            asyncio.create_task(
                _run_translation_inner(str(task.id), {"upload_key": upload_key})
            )
            logger.info("tasks.enqueued", task_id=str(task.id), backend="direct")

        try:
            await publish_progress(
                task.id,
                0,
                status="pending",
                message="queued",
            )
        except Exception:
            pass

        return TaskCreateResponse(
            task_id=str(task.id),
            status="pending",
            cached=False,
            cached_from=None,
            filename=task.filename,
            file_size=task.file_size,
            page_count=task.page_count,
            expires_at=task.expires_at,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_request", "error": str(exc)},
        )
    except Exception as exc:
        logger.exception("tasks.create.failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "internal_error", "error": str(exc)},
        )


@router.get(
    "",
    summary="列出当前用户的翻译任务",
)
async def list_tasks(
    db: DbSession,
    user: User = Depends(get_current_active_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> TaskListResponse:
    tasks = await task_service.list_user_tasks(
        db,
        user,
        page=page,
        page_size=page_size,
    )
    total = await task_service.count_user_tasks(db, user)
    return TaskListResponse(
        items=[_serialize_task(t) for t in tasks],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/{task_id}",
    summary="查询单个任务详情",
)
async def get_task(
    task_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(get_current_active_user),
) -> JSONResponse:
    task = await task_service.get_task_for_user(db, user, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "task_not_found"},
        )
    snapshot = await get_progress_snapshot(task.id)
    payload = _serialize_task(task)
    if snapshot:
        payload["progress_snapshot"] = snapshot
    return JSONResponse(content=payload)


@router.delete(
    "/{task_id}",
    summary="取消/删除任务",
)
async def delete_task(
    task_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(get_current_active_user),
) -> JSONResponse:
    task = await task_service.get_task_for_user(db, user, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "task_not_found"},
        )
    if task.status in {TaskStatus.PENDING, TaskStatus.PROCESSING}:
        ok = await task_service.cancel_task(db, user, task_id)
        await db.commit()
        return JSONResponse(content={"cancelled": ok, "status": "cancelled"})
    try:
        storage = get_storage()
        for key in (
            task.source_url,
            task.result_url,
            task.result_mono_url,
            task.result_md_url,
            task.result_docx_url,
        ):
            if key and isinstance(key, str):
                await storage.delete(key)
    except Exception as exc:
        logger.warning("tasks.delete.cleanup_failed", error=str(exc))
    await db.delete(task)
    await db.commit()
    return JSONResponse(content={"deleted": True})


@router.get(
    "/{task_id}/download",
    summary="下载翻译结果（302 跳转到签名 URL）",
)
async def download_task(
    task_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(get_current_active_user),
    format: Literal["pdf", "mono", "monolingual", "dual", "markdown", "md", "docx"] = Query(
        default="pdf",
        alias="format",
    ),
    type: Literal["dual", "mono"] | None = Query(
        default=None,
        alias="type",
        description="当 format=pdf 时,用 type 区分双语/纯译文",
    ),
) -> RedirectResponse:
    task = await task_service.get_task_for_user(db, user, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "task_not_found"},
        )
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "task_not_completed",
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            },
        )
    now_utc = datetime.now(timezone.utc)
    expires = task.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires < now_utc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "file_expired", "expires_at": task.expires_at.isoformat()},
        )

    target_url: str | None = None
    fmt = format.lower()
    if fmt in {"pdf", "dual"}:
        if type == "mono":
            target_url = task.result_mono_url or task.result_url
        else:
            target_url = task.result_url
    elif fmt in {"mono", "monolingual"}:
        target_url = task.result_mono_url or task.result_url
    elif fmt in {"markdown", "md"}:
        # HIDDEN-FEATURE: md 导出临时禁用
        if not settings.enable_markdown_export:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "code": "feature_disabled",
                    "feature": "markdown_export",
                    "message": "Markdown 导出功能已暂停,敬请期待。",
                },
            )
        target_url = task.result_md_url
    elif fmt == "docx":
        # HIDDEN-FEATURE: docx 导出临时禁用
        if not settings.enable_docx_export:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "code": "feature_disabled",
                    "feature": "docx_export",
                    "message": "Word 文档导出功能已暂停,敬请期待。",
                },
            )
        target_url = task.result_docx_url
    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "format_not_available", "format": fmt},
        )

    return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)


@router.websocket("/{task_id}/ws")
async def task_websocket(
    websocket: WebSocket,
    task_id: uuid.UUID,
    token: str | None = Query(default=None),
) -> None:
    await websocket.accept()
    auth_token = token
    if not auth_token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            auth_token = auth_header.split(" ", 1)[1]
    if not auth_token:
        await websocket.send_json(
            {"event": "error", "code": "unauthorized", "detail": "missing token"}
        )
        await websocket.close(code=4401, reason="unauthorized")
        return
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            user = await get_current_user_from_token(auth_token, session)
            if not user or not user.is_active:
                await websocket.send_json(
                    {"event": "error", "code": "unauthorized"}
                )
                await websocket.close(code=4401, reason="unauthorized")
                return
        except Exception as exc:
            logger.warning("ws.auth_failed", error=str(exc))
            await websocket.send_json({"event": "error", "code": "unauthorized"})
            await websocket.close(code=4401, reason="unauthorized")
            return
        task = await task_service.get_task_for_user(session, user, task_id)
        if task is None:
            await websocket.send_json(
                {"event": "error", "code": "task_not_found"}
            )
            await websocket.close(code=4404, reason="task not found")
            return
        initial_snapshot = await get_progress_snapshot(task.id)
        initial_payload: dict[str, Any] = {
            "event": "snapshot",
            "task_id": str(task.id),
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "progress": task.progress,
            "cached": False,
        }
        if initial_snapshot:
            initial_payload.update(initial_snapshot)
        await websocket.send_json(initial_payload)

    try:
        async for event in subscribe_progress(task.id, snapshot=None):
            try:
                await websocket.send_json(event)
            except Exception:
                break
            status_val = str(event.get("status") or "").lower()
            if status_val in {"completed", "failed", "cancelled"}:
                break
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.warning("ws.subscribe_error", error=str(exc))
    finally:
        try:
            await websocket.close(code=1000, reason="done")
        except Exception:
            pass


def _serialize_task(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "user_id": str(task.user_id),
        "filename": task.filename,
        "file_hash": task.file_hash,
        "file_size": task.file_size,
        "page_count": task.page_count,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "progress": task.progress,
        "source_language": task.source_language,
        "target_language": task.target_language,
        "llm_service": task.llm_service,
        "glossary_id": str(task.glossary_id) if task.glossary_id else None,
        "result_url": task.result_url,
        "result_mono_url": task.result_mono_url,
        "result_md_url": task.result_md_url,
        "result_docx_url": task.result_docx_url,
        "error_message": task.error_message,
        "cost_cny": float(task.cost_cny or 0),
        "prompt_tokens": task.prompt_tokens or 0,
        "completion_tokens": task.completion_tokens or 0,
        "options": task.options or {},
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "expires_at": task.expires_at.isoformat() if task.expires_at else None,
    }


__all__ = ["router"]