from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,  # noqa: F401 — 类型提示保留,实际用 duck typing 判断
    status,
)
# 备注:fastapi.UploadFile 与 starlette.datastructures.UploadFile 是不同类,
# multipart 解析出来的对象实际是 starlette 那一支。直接用 duck typing
# (hasattr(file, 'read')) 替代 isinstance,避免类比较失败。
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.glossary import Glossary
from app.models.quota import Quota, QuotaTier
from app.schemas.glossary import (
    GlossaryCsvImportRequest,
    GlossaryDetailResponse,
    GlossaryResponse,
    GlossaryUpdate,
)
from app.services import glossary_service


router: APIRouter = APIRouter()
logger = get_logger(__name__)
TIER_NAMES = {
    QuotaTier.FREE: "免费档",
    QuotaTier.STANDARD: "标准档",
    QuotaTier.PRO: "Pro 档",
}


async def _load_user_tier(db: AsyncSession, user_id: uuid.UUID) -> QuotaTier:
    result = await db.execute(select(Quota).where(Quota.user_id == user_id))
    quota = result.scalar_one_or_none()
    if quota is None:
        return QuotaTier.FREE
    return quota.tier


def _to_response(glossary: Glossary) -> GlossaryResponse:
    return GlossaryResponse(
        id=str(glossary.id),
        user_id=str(glossary.user_id) if glossary.user_id else None,
        name=glossary.name,
        description=glossary.description,
        domain=glossary.domain,
        term_count=glossary.term_count,
        is_active=glossary.is_active,
        is_builtin=glossary.is_builtin,
        is_system=glossary.is_system,
        created_at=glossary.created_at,
        updated_at=glossary.updated_at,
    )


def _to_detail_response(glossary: Glossary) -> GlossaryDetailResponse:
    return GlossaryDetailResponse(
        id=str(glossary.id),
        user_id=str(glossary.user_id) if glossary.user_id else None,
        name=glossary.name,
        description=glossary.description,
        domain=glossary.domain,
        term_count=glossary.term_count,
        is_active=glossary.is_active,
        is_builtin=glossary.is_builtin,
        is_system=glossary.is_system,
        created_at=glossary.created_at,
        updated_at=glossary.updated_at,
        terms=glossary.terms or [],
    )


async def _enforce_quota(db: AsyncSession, user_id: uuid.UUID) -> QuotaTier:
    tier = await _load_user_tier(db, user_id)
    current_count = await glossary_service.count_user_glossaries_for_user_id(db, user_id)
    quota_check = glossary_service.check_quota_for_tier(tier, current_count)
    if not quota_check.allowed:
        if quota_check.reason == "free_tier_cannot_create_glossary":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "free_tier_cannot_create_glossary",
                    "message": "免费档用户无法上传自定义术语库，请升级套餐",
                    "tier": tier.value,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": quota_check.reason or "glossary_quota_exceeded",
                "message": (
                    f"已达到 {TIER_NAMES.get(tier, tier.value)} 术语库数量上限"
                    f" ({quota_check.max_count})，请升级套餐"
                ),
                "tier": tier.value,
                "current_count": quota_check.current_count,
                "max_count": quota_check.max_count,
            },
        )
    return tier


async def _create_glossary_from_terms(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    parsed_terms: list[dict[str, Any]],
    description: str | None,
    domain: str,
) -> Glossary:
    await _enforce_quota(db, user_id)
    errors = glossary_service.validate_glossary_terms(parsed_terms)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "validation_failed",
                "message": "术语校验未通过",
                "errors": errors[:20],
            },
        )

    user = await glossary_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "user_not_found", "message": "用户不存在"},
        )

    glossary = await glossary_service.create_glossary(
        db,
        user,
        name=name.strip(),
        terms=parsed_terms,
        description=description,
        domain=domain,
    )
    await db.commit()
    await db.refresh(glossary)
    return glossary


@router.post(
    "",
    response_model=GlossaryDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传自定义术语库（multipart CSV 或 JSON body）",
)
async def create_glossary(
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> GlossaryDetailResponse:
    content_type = (request.headers.get("content-type") or "").lower()
    logger.info("glossaries.create.content_type", content_type=content_type)

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        file = form.get("file")
        name = form.get("name")
        description = form.get("description")
        domain = form.get("domain")
        logger.info("glossaries.create.form", file_type=str(type(file) if file else None), name=str(name)[:80])

        parsed_terms: list[dict[str, Any]] = []
        # duck typing: multipart 解析出的 file 对象有 .read/.filename,
        # 不依赖具体的 UploadFile 类来源
        if file is not None and hasattr(file, "read") and hasattr(file, "filename"):
            raw = await file.read()
            if not raw:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "empty_file",
                        "message": "上传的 CSV 文件为空",
                    },
                )
            parse_result = glossary_service.parse_csv(raw)
            parsed_terms = glossary_service.terms_to_dicts(parse_result.terms)
            if not parsed_terms:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "no_valid_terms",
                        "message": "CSV 文件未能解析出任何合法术语",
                        "warnings": parse_result.warnings,
                    },
                )
            if not name:
                original = file.filename or "uploaded"
                name = original.rsplit(".", 1)[0][:128] or "未命名术语库"
        else:
            terms_json = form.get("terms_json")
            if terms_json:
                try:
                    data = json.loads(terms_json)
                except json.JSONDecodeError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "code": "invalid_terms_json",
                            "message": f"terms_json 无法解析: {exc}",
                        },
                    ) from exc
                if isinstance(data, dict):
                    name = name or data.get("name")
                    description = description or data.get("description")
                    domain = domain or data.get("domain") or "general"
                    raw_terms = data.get("terms") or []
                    if not isinstance(raw_terms, list):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "code": "invalid_terms_json",
                                "message": "terms 必须为数组",
                            },
                        )
                    parsed_terms = glossary_service.terms_to_dicts(raw_terms)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "missing_input",
                        "message": "请提供 CSV 文件（file 字段）或 terms_json 字段",
                    },
                )

        if not name or not str(name).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "missing_name",
                    "message": "请提供术语库名称（name）",
                },
            )

        glossary = await _create_glossary_from_terms(
            db,
            user.id,
            str(name),
            parsed_terms,
            str(description) if description else None,
            str(domain) if domain else "general",
        )
        return _to_detail_response(glossary)

    if content_type.startswith("application/json"):
        try:
            raw_body = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_json",
                    "message": f"请求体不是合法 JSON: {exc}",
                },
            ) from exc
        try:
            payload = GlossaryCsvImportRequest.model_validate(raw_body)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "validation_failed",
                    "message": f"JSON body 校验失败: {exc}",
                },
            ) from exc

        parsed_terms = glossary_service.terms_to_dicts(
            [t.model_dump() for t in payload.terms]
        )
        glossary = await _create_glossary_from_terms(
            db,
            user.id,
            payload.name,
            parsed_terms,
            payload.description,
            payload.domain,
        )
        return _to_detail_response(glossary)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail={
            "code": "unsupported_media_type",
            "message": (
                "请使用 multipart/form-data (含 file=CSV) 或 application/json 提交"
            ),
        },
    )


@router.get(
    "",
    response_model=list[GlossaryResponse],
    summary="列出当前用户可见的全部术语库（包含系统词库）",
)
async def list_glossaries(
    db: DbSession,
    user: CurrentUser,
    include_system: bool = Query(default=True),
) -> list[GlossaryResponse]:
    glossaries = await glossary_service.list_user_glossaries(
        db, user, include_system=include_system
    )
    return [_to_response(g) for g in glossaries]


@router.get(
    "/{glossary_id}",
    response_model=GlossaryDetailResponse,
    summary="获取术语库详情",
)
async def get_glossary(
    db: DbSession,
    user: CurrentUser,
    glossary_id: uuid.UUID,
) -> GlossaryDetailResponse:
    glossary = await glossary_service.get_glossary_for_user(db, user, glossary_id)
    if glossary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "glossary_not_found",
                "message": "术语库不存在或无权访问",
            },
        )
    return _to_detail_response(glossary)


@router.patch(
    "/{glossary_id}",
    response_model=GlossaryDetailResponse,
    summary="更新术语库（名称或术语）",
)
async def update_glossary_endpoint(
    db: DbSession,
    user: CurrentUser,
    glossary_id: uuid.UUID,
    payload: GlossaryUpdate,
) -> GlossaryDetailResponse:
    existing = await glossary_service.get_owned_glossary_for_user(
        db, user, glossary_id
    )
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "glossary_not_found",
                "message": "术语库不存在或无权修改（系统词库不可编辑）",
            },
        )

    terms_input = (
        [t.model_dump() for t in payload.terms] if payload.terms is not None else None
    )
    if terms_input is not None:
        errors = glossary_service.validate_glossary_terms(terms_input)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "validation_failed",
                    "message": "术语校验未通过",
                    "errors": errors[:20],
                },
            )

    glossary = await glossary_service.update_glossary(
        db,
        user,
        glossary_id,
        name=payload.name,
        terms=terms_input,
        description=payload.description,
        is_active=payload.is_active,
    )
    if glossary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "glossary_not_found",
                "message": "术语库不存在或无权修改",
            },
        )
    await db.commit()
    await db.refresh(glossary)
    return _to_detail_response(glossary)


@router.delete(
    "/{glossary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除术语库",
)
async def delete_glossary(
    db: DbSession,
    user: CurrentUser,
    glossary_id: uuid.UUID,
) -> Response:
    ok = await glossary_service.delete_glossary(db, user, glossary_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "glossary_not_found",
                "message": "术语库不存在或无权删除（系统词库不可删除）",
            },
        )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{glossary_id}/export",
    summary="导出术语库为 CSV 文件",
    responses={
        200: {
            "content": {
                "text/csv": {},
            },
            "description": "返回 CSV 文件流（utf-8-sig 编码）",
        },
    },
)
async def export_glossary(
    db: DbSession,
    user: CurrentUser,
    glossary_id: uuid.UUID,
) -> Response:
    glossary = await glossary_service.get_glossary_for_user(db, user, glossary_id)
    if glossary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "glossary_not_found",
                "message": "术语库不存在或无权访问",
            },
        )
    body = glossary_service.export_glossary_csv(glossary)
    # HTTP headers 必须是 ASCII;中文名用 ASCII 兜底 + RFC 5987 percent-encoded
    safe_name = (glossary.name or "glossary").encode("ascii", "replace").decode("ascii")
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in safe_name) or "glossary"
    ascii_name = f"{safe_name}_{glossary.id}.csv"
    utf8_name = f"{glossary.name or 'glossary'}_{glossary.id}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(utf8_name, safe='')}"
            ),
            "X-Glossary-Term-Count": str(glossary.term_count or 0),
        },
    )


@router.get(
    "/{glossary_id}/prompt",
    summary="预览术语库对应的 LLM prompt 片段（调试用）",
)
async def preview_prompt(
    db: DbSession,
    user: CurrentUser,
    glossary_id: uuid.UUID,
) -> dict[str, str]:
    glossary = await glossary_service.get_glossary_for_user(db, user, glossary_id)
    if glossary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "glossary_not_found",
                "message": "术语库不存在或无权访问",
            },
        )
    prompt = glossary_service.build_glossary_prompt(glossary)
    return {"prompt": prompt}


__all__ = ["router", "create_glossary", "list_glossaries", "get_glossary"]