from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.glossary import Glossary
from app.services.glossary_service import MAX_CONTEXT_LENGTH, MAX_TERM_LENGTH, MAX_TRANSLATION_LENGTH, parse_csv


logger = get_logger(__name__)


SEED_DIR: Path = Path(__file__).resolve().parent.parent / "seed_glossary"


@dataclass(slots=True)
class SeedManifestEntry:
    name: str
    domain: str
    file_path: Path
    description: str = ""
    version: str = "1.0.0"


SEED_MANIFEST: tuple[SeedManifestEntry, ...] = (
    SeedManifestEntry(
        name="内置 · CS / AI / ML 术语库",
        domain="cs_ai",
        file_path=SEED_DIR / "cs_ai.csv",
        description=(
            "覆盖神经网络、训练、评估、经典模型、数学基础等领域的"
            "中英文术语对照表，系统内置、只读。"
        ),
        version="1.0.0",
    ),
)


@dataclass(slots=True)
class SeedLoadResult:
    inserted: int
    skipped_existing: int
    updated: int
    total_terms: int
    files: list[str]


def _slugify(value: str) -> str:
    safe = []
    for ch in value.lower():
        if ch.isalnum():
            safe.append(ch)
        elif ch in (" ", "_", "-", ".", "/"):
            safe.append("_")
    slug = "".join(safe).strip("_")
    return slug or uuid.uuid4().hex[:8]


def _seed_signature(entry: SeedManifestEntry, terms: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "name": entry.name,
        "domain": entry.domain,
        "version": entry.version,
        "terms_count": len(terms),
        "term_hashes": sorted(
            f"{t.get('term','').strip().lower()}|{t.get('translation','').strip()}"
            for t in terms[:50]
        ),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    import hashlib

    return {"version": entry.version, "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}


def _normalize_seed_terms(parsed_terms: Iterable[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for raw in parsed_terms:
        if hasattr(raw, "term"):
            term = str(getattr(raw, "term") or "").strip()
            translation = str(getattr(raw, "translation") or "").strip()
            context = getattr(raw, "context", None)
        else:
            term = str(raw.get("term") or "").strip()
            translation = str(raw.get("translation") or "").strip()
            context = raw.get("context")
        if not term or not translation:
            continue
        serialized.append(
            {
                "term": term[:MAX_TERM_LENGTH],
                "translation": translation[:MAX_TRANSLATION_LENGTH],
                "context": (
                    str(context)[:MAX_CONTEXT_LENGTH] if context else None
                ),
            }
        )
    dedup: dict[str, dict[str, Any]] = {}
    for item in serialized:
        dedup[item["term"].lower()] = item
    return list(dedup.values())


async def get_system_glossaries(db: AsyncSession) -> list[Glossary]:
    result = await db.execute(
        select(Glossary)
        .where(Glossary.is_system.is_(True))
        .order_by(Glossary.name.asc())
    )
    return list(result.scalars().all())


async def _find_system_by_name(db: AsyncSession, name: str) -> Glossary | None:
    result = await db.execute(
        select(Glossary).where(
            Glossary.is_system.is_(True), Glossary.name == name
        )
    )
    return result.scalar_one_or_none()


async def load_seed_glossaries(db: AsyncSession) -> SeedLoadResult:
    inserted = 0
    updated = 0
    skipped_existing = 0
    total_terms = 0
    files: list[str] = []

    for entry in SEED_MANIFEST:
        path = entry.file_path
        if not path.is_file():
            logger.warning(
                "seed.file_missing",
                name=entry.name,
                path=str(path),
            )
            continue
        files.append(str(path))

        raw = path.read_bytes()
        parse_result = parse_csv(raw)
        if parse_result.warnings:
            logger.info(
                "seed.parse_warnings",
                name=entry.name,
                warnings=parse_result.warnings,
            )
        terms = _normalize_seed_terms(parse_result.terms)
        if not terms:
            logger.warning(
                "seed.no_terms",
                name=entry.name,
                path=str(path),
            )
            continue

        signature = _seed_signature(entry, terms)
        existing = await _find_system_by_name(db, entry.name)

        if existing is None:
            glossary = Glossary(
                id=uuid.uuid4(),
                user_id=None,
                name=entry.name,
                description=entry.description,
                domain=entry.domain,
                terms=terms,
                term_count=len(terms),
                is_active=True,
                is_builtin=True,
                is_system=True,
            )
            db.add(glossary)
            inserted += 1
            total_terms += len(terms)
            logger.info(
                "seed.inserted",
                name=entry.name,
                term_count=len(terms),
                domain=entry.domain,
            )
            continue

        existing_signature = (existing.description or "").strip()
        same_signature = (
            f"v={signature['version']} sha={signature['sha256']}" in existing_signature
        )

        if same_signature:
            skipped_existing += 1
            total_terms += existing.term_count or len(terms)
            logger.info(
                "seed.skipped_unchanged",
                name=entry.name,
                term_count=existing.term_count,
            )
            continue

        existing.terms = terms
        existing.term_count = len(terms)
        existing.domain = entry.domain
        existing.description = (
            f"{entry.description}\n[v={signature['version']} sha={signature['sha256']}]"
        ).strip()
        existing.is_builtin = True
        existing.is_active = True
        updated += 1
        total_terms += len(terms)
        logger.info(
            "seed.updated",
            name=entry.name,
            term_count=len(terms),
        )

    if inserted or updated:
        await db.commit()

    return SeedLoadResult(
        inserted=inserted,
        skipped_existing=skipped_existing,
        updated=updated,
        total_terms=total_terms,
        files=files,
    )


__all__ = [
    "SeedManifestEntry",
    "SeedLoadResult",
    "SEED_MANIFEST",
    "load_seed_glossaries",
    "get_system_glossaries",
]