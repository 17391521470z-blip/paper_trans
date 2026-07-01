from __future__ import annotations

import csv
import io
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import Glossary
from app.models.quota import QuotaTier
from app.models.user import User


TERM_HEADERS = {"term", "source", "src", "word", "原文"}
TRANSLATION_HEADERS = {"translation", "target", "trans", "译文", "翻译"}
CONTEXT_HEADERS = {"context", "note", "context_optional", "注释"}

MAX_TERMS_PER_GLOSSARY = 1000  # 单个用户术语库词条上限
MAX_TERM_LENGTH = 255
MAX_TRANSLATION_LENGTH = 255
MAX_CONTEXT_LENGTH = 512
MAX_PROMPT_TERMS = 500
MAX_PROMPT_CHARS = 8000

TIER_LIMITS: dict[QuotaTier, int | None] = {
    QuotaTier.FREE: 0,
    QuotaTier.STANDARD: 1,
    QuotaTier.PRO: 5,
}


@dataclass(slots=True)
class ParsedTerm:
    term: str
    translation: str
    context: str | None


@dataclass(slots=True)
class GlossaryParseResult:
    terms: list[ParsedTerm]
    skipped: int
    warnings: list[str]


@dataclass(slots=True)
class QuotaCheckResult:
    allowed: bool
    current_count: int
    max_count: int | None
    reason: str | None = None


def _detect_column(headers: Sequence[str], candidates: set[str]) -> int | None:
    lowered = [h.strip().lower() for h in headers]
    for idx, header in enumerate(lowered):
        if header in candidates:
            return idx
    for idx, header in enumerate(lowered):
        for cand in candidates:
            if cand in header:
                return idx
    return None


def _decode_bytes(blob: bytes | str) -> str:
    if isinstance(blob, str):
        return blob
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return blob.decode(encoding)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="replace")


def _sniff_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def parse_csv(blob: bytes | str, *, max_rows: int = 10000) -> GlossaryParseResult:
    text = _decode_bytes(blob)

    if not text.strip():
        return GlossaryParseResult(terms=[], skipped=0, warnings=["empty csv"])

    sample = text[:4096]
    dialect = _sniff_dialect(sample)
    reader = csv.reader(io.StringIO(text), dialect=dialect)

    try:
        headers = next(reader)
    except StopIteration:
        return GlossaryParseResult(terms=[], skipped=0, warnings=["empty csv"])

    term_col = _detect_column(headers, TERM_HEADERS)
    trans_col = _detect_column(headers, TRANSLATION_HEADERS)
    context_col = _detect_column(headers, CONTEXT_HEADERS)

    if term_col is None or trans_col is None:
        return GlossaryParseResult(
            terms=[],
            skipped=0,
            warnings=[
                "missing required columns: need 'term' and 'translation'",
            ],
        )

    warnings: list[str] = []
    parsed: list[ParsedTerm] = []
    seen: set[str] = set()
    skipped = 0

    for row_num, row in enumerate(reader, start=2):
        if row_num - 1 > max_rows:
            warnings.append(f"exceeded max_rows={max_rows}, stopped reading")
            break
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) <= max(term_col, trans_col):
            skipped += 1
            continue
        term = (row[term_col] or "").strip()
        translation = (row[trans_col] or "").strip()
        if not term or not translation:
            skipped += 1
            continue
        if len(term) > MAX_TERM_LENGTH:
            term = term[:MAX_TERM_LENGTH]
        if len(translation) > MAX_TRANSLATION_LENGTH:
            translation = translation[:MAX_TRANSLATION_LENGTH]
        context: str | None = None
        if context_col is not None and len(row) > context_col:
            ctx_raw = (row[context_col] or "").strip()
            if ctx_raw:
                context = ctx_raw[:MAX_CONTEXT_LENGTH]
        key = term.lower()
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        parsed.append(ParsedTerm(term=term, translation=translation, context=context))

    return GlossaryParseResult(terms=parsed, skipped=skipped, warnings=warnings)


def terms_to_dicts(terms: Iterable[ParsedTerm | dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for t in terms:
        if isinstance(t, ParsedTerm):
            result.append(
                {
                    "term": t.term,
                    "translation": t.translation,
                    "context": t.context,
                }
            )
        else:
            result.append(
                {
                    "term": str(t.get("term", "")),
                    "translation": str(t.get("translation", "")),
                    "context": t.get("context"),
                }
            )
    return result


def _term_dict_from_obj(obj: ParsedTerm | dict[str, Any]) -> dict[str, Any]:
    if isinstance(obj, ParsedTerm):
        return {"term": obj.term, "translation": obj.translation, "context": obj.context}
    return {
        "term": str(obj.get("term", "")),
        "translation": str(obj.get("translation", "")),
        "context": obj.get("context"),
    }


def validate_glossary_terms(
    terms: Iterable[dict[str, Any] | ParsedTerm],
    *,
    max_terms: int = MAX_TERMS_PER_GLOSSARY,
) -> list[str]:
    errors: list[str] = []
    term_count = 0
    seen: set[str] = set()

    for index, raw in enumerate(terms, start=1):
        item = _term_dict_from_obj(raw)
        term = (item.get("term") or "").strip()
        translation = (item.get("translation") or "").strip()
        context = item.get("context")

        if not term:
            errors.append(f"row {index}: term is empty")
            continue
        if not translation:
            errors.append(f"row {index}: translation is empty for '{term}'")
            continue
        if len(term) > MAX_TERM_LENGTH:
            errors.append(
                f"row {index}: term '{term[:32]}...' exceeds {MAX_TERM_LENGTH} chars"
            )
        if len(translation) > MAX_TRANSLATION_LENGTH:
            errors.append(
                f"row {index}: translation for '{term[:32]}' exceeds "
                f"{MAX_TRANSLATION_LENGTH} chars"
            )
        if context is not None and len(str(context)) > MAX_CONTEXT_LENGTH:
            errors.append(
                f"row {index}: context for '{term[:32]}' exceeds "
                f"{MAX_CONTEXT_LENGTH} chars"
            )

        key = term.lower()
        if key in seen:
            errors.append(f"row {index}: duplicate term '{term}'")
        else:
            seen.add(key)
        term_count += 1

    if term_count > max_terms:
        errors.append(f"too many terms: {term_count} > {max_terms}")

    return errors


def _serialize_terms(
    terms: Sequence[dict[str, Any] | ParsedTerm],
) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for raw in terms:
        item = _term_dict_from_obj(raw)
        term = (item.get("term") or "").strip()
        translation = (item.get("translation") or "").strip()
        context = item.get("context")
        if not term or not translation:
            continue
        key = term.lower()
        deduped[key] = {
            "term": term[:MAX_TERM_LENGTH],
            "translation": translation[:MAX_TRANSLATION_LENGTH],
            "context": (str(context)[:MAX_CONTEXT_LENGTH] if context else None),
        }
    return list(deduped.values())


async def count_user_glossaries(db: AsyncSession, user: User) -> int:
    return await count_user_glossaries_for_user_id(db, user.id)


async def count_user_glossaries_for_user_id(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Glossary.id))
        .where(Glossary.user_id == user_id)
        .where(Glossary.is_system.is_(False))
    )
    return int(result.scalar_one() or 0)


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def check_quota_for_tier(tier: QuotaTier, current_count: int) -> QuotaCheckResult:
    max_count = TIER_LIMITS.get(tier, 0)
    if max_count is None:
        return QuotaCheckResult(
            allowed=True, current_count=current_count, max_count=None
        )
    if tier == QuotaTier.FREE:
        return QuotaCheckResult(
            allowed=False,
            current_count=current_count,
            max_count=max_count,
            reason="free_tier_cannot_create_glossary",
        )
    if current_count >= max_count:
        return QuotaCheckResult(
            allowed=False,
            current_count=current_count,
            max_count=max_count,
            reason="glossary_quota_exceeded",
        )
    return QuotaCheckResult(
        allowed=True, current_count=current_count, max_count=max_count
    )


async def create_glossary(
    db: AsyncSession,
    user: User,
    name: str,
    terms: Sequence[dict[str, Any] | ParsedTerm],
    *,
    description: str | None = None,
    domain: str = "general",
    is_active: bool = True,
) -> Glossary:
    serialized = _serialize_terms(terms)
    glossary = Glossary(
        user_id=user.id,
        name=name,
        description=description,
        domain=domain,
        terms=serialized,
        term_count=len(serialized),
        is_active=is_active,
        is_builtin=False,
        is_system=False,
    )
    db.add(glossary)
    await db.flush()
    await db.refresh(glossary)
    return glossary


async def list_user_glossaries(
    db: AsyncSession,
    user: User,
    *,
    include_system: bool = True,
) -> list[Glossary]:
    stmt = select(Glossary).where(Glossary.user_id == user.id)
    if include_system:
        stmt = stmt.order_by(Glossary.is_system.desc(), Glossary.created_at.desc())
    else:
        stmt = stmt.order_by(Glossary.created_at.desc())
    result = await db.execute(stmt)
    user_list = list(result.scalars().all())

    if not include_system:
        return user_list

    sys_result = await db.execute(
        select(Glossary)
        .where(Glossary.is_system.is_(True))
        .order_by(Glossary.name.asc())
    )
    sys_list = list(sys_result.scalars().all())
    return sys_list + user_list


async def list_user_owned_glossaries(db: AsyncSession, user: User) -> list[Glossary]:
    result = await db.execute(
        select(Glossary)
        .where(Glossary.user_id == user.id)
        .where(Glossary.is_system.is_(False))
        .order_by(Glossary.created_at.desc())
    )
    return list(result.scalars().all())


async def get_glossary_for_user(
    db: AsyncSession,
    user: User,
    glossary_id: uuid.UUID,
) -> Glossary | None:
    result = await db.execute(select(Glossary).where(Glossary.id == glossary_id))
    glossary = result.scalar_one_or_none()
    if glossary is None:
        return None
    if glossary.is_system:
        return glossary
    if glossary.user_id != user.id:
        return None
    return glossary


async def get_owned_glossary_for_user(
    db: AsyncSession,
    user: User,
    glossary_id: uuid.UUID,
) -> Glossary | None:
    result = await db.execute(select(Glossary).where(Glossary.id == glossary_id))
    glossary = result.scalar_one_or_none()
    if glossary is None:
        return None
    if glossary.is_system:
        return None
    if glossary.user_id != user.id:
        return None
    return glossary


async def update_glossary(
    db: AsyncSession,
    user: User,
    glossary_id: uuid.UUID,
    *,
    name: str | None = None,
    terms: Sequence[dict[str, Any] | ParsedTerm] | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> Glossary | None:
    glossary = await get_owned_glossary_for_user(db, user, glossary_id)
    if glossary is None:
        return None
    if name is not None:
        glossary.name = name
    if description is not None:
        glossary.description = description
    if is_active is not None:
        glossary.is_active = is_active
    if terms is not None:
        serialized = _serialize_terms(terms)
        glossary.terms = serialized
        glossary.term_count = len(serialized)
    await db.flush()
    await db.refresh(glossary)
    return glossary


async def delete_glossary(db: AsyncSession, user: User, glossary_id: uuid.UUID) -> bool:
    glossary = await get_owned_glossary_for_user(db, user, glossary_id)
    if glossary is None:
        return False
    await db.delete(glossary)
    await db.flush()
    return True


def export_glossary_csv(glossary: Glossary) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect=csv.excel)
    writer.writerow(["term", "translation", "context"])
    terms = glossary.terms or []
    for raw in terms:
        if isinstance(raw, dict):
            writer.writerow(
                [
                    raw.get("term", ""),
                    raw.get("translation", ""),
                    raw.get("context") or "",
                ]
            )
        else:
            writer.writerow([str(raw), "", ""])
    return buffer.getvalue().encode("utf-8-sig")


def _format_single_term(item: dict[str, Any]) -> str:
    term = str(item.get("term") or "").strip()
    translation = str(item.get("translation") or "").strip()
    if not term or not translation:
        return ""
    line = f'- "{term}" → "{translation}"'
    context = item.get("context")
    if context:
        line += f"  ({context})"
    return line


def merge_terms(
    glossaries: Iterable[Glossary | None],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for gloss in glossaries:
        if gloss is None:
            continue
        terms = gloss.terms or []
        for raw in terms:
            if not isinstance(raw, dict):
                continue
            term = str(raw.get("term") or "").strip()
            translation = str(raw.get("translation") or "").strip()
            if not term or not translation:
                continue
            key = term.lower()
            merged[key] = {
                "term": term,
                "translation": translation,
                "context": raw.get("context"),
            }
    return list(merged.values())


def build_glossary_prompt(
    glossary: Glossary | Sequence[Glossary] | None,
    *,
    max_terms: int = MAX_PROMPT_TERMS,
    max_chars: int = MAX_PROMPT_CHARS,
) -> str:
    if glossary is None:
        return ""
    glossaries = glossary if isinstance(glossary, Sequence) else [glossary]
    glossaries = [g for g in glossaries if g is not None]
    if not glossaries:
        return ""

    merged = merge_terms(glossaries)
    if not merged:
        return ""

    lines: list[str] = []
    lines.append("请使用以下术语对照表（术语必须严格按下表翻译，禁止替换或意译）：")
    used = 0
    for item in merged:
        line = _format_single_term(item)
        if not line:
            continue
        if used >= max_terms:
            break
        if sum(len(x) for x in lines) + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += 1

    if used == 0:
        return ""
    if used < len(merged):
        lines.append(
            f"...（共 {len(merged)} 条术语，prompt 已截断前 {used} 条；"
            f"请按上下文与领域惯例翻译其余内容）"
        )
    return "\n".join(lines)


async def resolve_task_glossaries(
    db: AsyncSession,
    user: User,
    glossary_ids: Sequence[uuid.UUID] | None,
) -> list[Glossary]:
    if not glossary_ids:
        result = await db.execute(
            select(Glossary)
            .where(Glossary.user_id == user.id)
            .where(Glossary.is_active.is_(True))
            .order_by(Glossary.created_at.asc())
        )
        return list(result.scalars().all())
    glossaries: list[Glossary] = []
    seen: set[uuid.UUID] = set()
    for gid in glossary_ids:
        if gid in seen:
            continue
        seen.add(gid)
        gloss = await get_glossary_for_user(db, user, gid)
        if gloss is not None and gloss.is_active:
            glossaries.append(gloss)
    return glossaries


_TERM_NORMALIZE_RE = re.compile(r"\s+")


def normalize_term(term: str) -> str:
    return _TERM_NORMALIZE_RE.sub(" ", term).strip()