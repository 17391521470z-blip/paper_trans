"""Load benchmark PDFs and convert them to translation-ready blocks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.services.pdf_blocks import Block, extract_blocks


def _convert_floats(obj: Any) -> Any:
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_floats(v) for v in obj]
    return obj


def blocks_to_json(blocks: list[Block]) -> list[dict[str, Any]]:
    return [_convert_floats(b.to_dict()) for b in blocks]


def load_or_extract_blocks(pdf_path: Path, cache_dir: Path) -> list[dict[str, Any]]:
    """Extract blocks from a PDF, caching the result as JSON."""
    cache_path = cache_dir / f"{pdf_path.stem}.blocks.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    blocks = extract_blocks(str(pdf_path))
    data = blocks_to_json(blocks)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def filter_translatable_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only blocks that should be translated by the LLM."""
    return [
        b for b in blocks
        if b.get("type") in {"title", "paragraph", "table_caption", "figure_caption"}
    ]


def discover_papers(papers_dir: Path) -> list[Path]:
    """Find all PDF files under the papers directory."""
    return sorted(papers_dir.glob("**/*.pdf"))
