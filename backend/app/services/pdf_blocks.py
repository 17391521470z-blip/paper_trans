"""Structured PDF block extraction using DocLayout + pdfplumber.

This module replaces the previous text-only extraction with a layout-aware
pipeline that identifies titles, paragraphs, figures, tables, and formulas.
"""
from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np

from app.core.logging import get_logger


logger = get_logger(__name__)


BlockType = Literal[
    "title",
    "paragraph",
    "figure",
    "figure_caption",
    "table",
    "table_caption",
    "formula",
    "abandon",
]


@dataclass(slots=True)
class Block:
    type: BlockType
    text: str
    page: int
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF points
    confidence: float = 0.0
    level: int = 0  # for titles: 1 / 2 / 3
    lang: Literal["source", "translation", "unknown"] = "unknown"
    children: list["Block"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "page": self.page,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
            "level": self.level,
            "lang": self.lang,
            "children": [c.to_dict() for c in self.children],
        }


# DocLayout class id -> block type
_CLASS_MAP: dict[int, BlockType] = {
    0: "title",
    1: "paragraph",
    2: "abandon",  # headers/footers/decorations
    3: "figure",
    4: "figure_caption",
    5: "table",
    6: "table_caption",
    7: "abandon",  # table_footnote -> treat as abandon for now
    8: "formula",
    9: "formula",  # formula_caption merged with formula block
}

# Class name to type (used when we only have names, not ids)
_NAME_MAP: dict[str, BlockType] = {
    "title": "title",
    "plain text": "paragraph",
    "abandon": "abandon",
    "figure": "figure",
    "figure_caption": "figure_caption",
    "table": "table",
    "table_caption": "table_caption",
    "table_footnote": "abandon",
    "isolate_formula": "formula",
    "formula_caption": "formula",
}


_MODEL_CACHE: dict[str, Any] = {}
_RENDER_DPI = 150  # DocLayout prediction DPI; PDF point = pixel / DPI * 72


def _get_layout_model() -> Any:
    """Load DocLayout ONNX model once and cache."""
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"]
    from babeldoc.docvision.doclayout import DocLayoutModel

    logger.info("doclayout.loading")
    t0 = time.time()
    model = DocLayoutModel.load_available()
    logger.info("doclayout.loaded", elapsed=round(time.time() - t0, 2))
    _MODEL_CACHE["model"] = model
    return model


def _render_page(doc: Any, page_idx: int) -> tuple[np.ndarray, int, int]:
    """Render a page to RGB numpy array at fixed DPI."""
    page = doc[page_idx]
    pix = page.get_pixmap(dpi=_RENDER_DPI)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    if pix.n == 4:
        img = img[:, :, :3]
    # PyMuDF gives RGB already, but babeldoc's doclayout expects RGB too
    return img, pix.width, pix.height


def _pix_bbox_to_pdf_bbox(
    xyxy: Iterable[float], img_w: int, img_h: int, page_w: float, page_h: float
) -> tuple[float, float, float, float]:
    """Convert pixel bbox to PDF point bbox.

    pdfplumber uses top-down y-axis (origin at top-left), the same as
    the image coordinate system, so no y inversion is needed.
    """
    x0, y0, x1, y1 = xyxy
    pdf_x0 = x0 / _RENDER_DPI * 72
    pdf_x1 = x1 / _RENDER_DPI * 72
    pdf_y0 = y0 / _RENDER_DPI * 72
    pdf_y1 = y1 / _RENDER_DPI * 72
    # Clamp to page bounds
    pdf_x0 = max(0.0, min(pdf_x0, page_w))
    pdf_x1 = max(0.0, min(pdf_x1, page_w))
    pdf_y0 = max(0.0, min(pdf_y0, page_h))
    pdf_y1 = max(0.0, min(pdf_y1, page_h))
    return (pdf_x0, pdf_y0, pdf_x1, pdf_y1)


def _classify_box(cls_id: int, names: dict[int, str]) -> BlockType:
    name = names.get(cls_id, "")
    return _NAME_MAP.get(name, _CLASS_MAP.get(cls_id, "paragraph"))


def _merge_words_into_lines(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group words into text lines based on vertical proximity."""
    if not words:
        return []
    # pdfplumber words are already in reading order; group by overlapping y
    lines: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_top: float | None = None
    current_bottom: float | None = None
    for w in words:
        top = w["top"]
        bottom = w["bottom"]
        if current and current_top is not None and (top - current_bottom) > 3:
            # new line
            lines.append(_finalize_line(current))
            current = []
        current.append(w)
        current_top = top if current_top is None else min(current_top, top)
        current_bottom = bottom if current_bottom is None else max(current_bottom, bottom)
    if current:
        lines.append(_finalize_line(current))
    return lines


def _finalize_line(words: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(w["text"] for w in words)
    return {
        "text": text,
        "x0": min(w["x0"] for w in words),
        "x1": max(w["x1"] for w in words),
        "top": min(w["top"] for w in words),
        "bottom": max(w["bottom"] for w in words),
    }


def _merge_lines_into_paragraph(
    lines: list[dict[str, Any]],
) -> tuple[str, tuple[float, float, float, float]]:
    """Merge lines into one paragraph string + overall bbox."""
    text = "\n".join(line["text"] for line in lines)
    bbox = (
        min(line["x0"] for line in lines),
        min(line["top"] for line in lines),
        max(line["x1"] for line in lines),
        max(line["bottom"] for line in lines),
    )
    return text, bbox


def _detect_title_level_by_fontsize(
    lines: list[dict[str, Any]], page_w: float
) -> int:
    """Heuristic: bigger font + centered = higher level title."""
    if not lines:
        return 1
    # Use first line's font size (pdfplumber words carry 'size')
    # If we have words in the lines, get max size
    sizes: list[float] = []
    for line in lines:
        for w in line.get("words", []):
            if w.get("size"):
                sizes.append(float(w["size"]))
    if not sizes:
        return 1
    avg_size = sum(sizes) / len(sizes)
    if avg_size >= 20:
        return 1
    if avg_size >= 14:
        return 2
    return 3


def _extract_text_in_bbox(
    plumber_page: Any, bbox: tuple[float, float, float, float]
) -> list[dict[str, Any]]:
    """Extract pdfplumber words inside a PDF bbox, with size/font info."""
    x0, y0, x1, y1 = bbox
    # small inset to avoid edge text bleeding in
    try:
        cropped = plumber_page.crop((x0, y0, x1, y1))
    except Exception:
        return []
    try:
        words = cropped.extract_words(
            keep_blank_chars=False,
            use_text_flow=True,
            extra_attrs=["size", "fontname"],
        ) or []
    except Exception:
        return []
    # Translate bbox-relative coords back to page coords
    out = []
    for w in words:
        out.append(
            {
                "text": w["text"],
                "x0": w["x0"] + x0,
                "x1": w["x1"] + x0,
                "top": w["top"] + y0,
                "bottom": w["bottom"] + y0,
                "size": w.get("size"),
                "fontname": w.get("fontname"),
            }
        )
    return out


def _process_page(
    page_idx: int,
    pymu_doc: Any,
    plumber_pdf: Any,
) -> list[Block]:
    """Extract blocks from a single page using DocLayout + pdfplumber."""
    page_no = page_idx + 1
    page = pymu_doc[page_idx]
    plumber_page = plumber_pdf.pages[page_idx]
    page_w = float(plumber_page.width)
    page_h = float(plumber_page.height)

    # Render + predict
    img, img_w, img_h = _render_page(pymu_doc, page_idx)
    model = _get_layout_model()
    results = model.predict(img, imgsz=1024)
    boxes = results[0].boxes
    names = results[0].names

    blocks: list[Block] = []
    for b in boxes:
        cls_id = int(b.cls)
        cls_name = names.get(cls_id, "")
        block_type = _NAME_MAP.get(cls_name, _CLASS_MAP.get(cls_id, "paragraph"))
        if block_type == "abandon":
            continue  # skip headers/footers/decorations

        xyxy = b.xyxy.squeeze()
        bbox = _pix_bbox_to_pdf_bbox(xyxy, img_w, img_h, page_w, page_h)
        x0, y0, x1, y1 = bbox
        if (x1 - x0) < 5 or (y1 - y0) < 5:
            continue  # too small

        words = _extract_text_in_bbox(plumber_page, bbox)
        if not words and block_type in {"title", "paragraph", "table_caption", "figure_caption"}:
            # text-bearing class but no text layer
            continue

        # Group words into lines, then into a single text
        lines = _merge_words_into_lines(words)
        if not lines and block_type in {"paragraph", "title"}:
            continue
        text, _ = (
            _merge_lines_into_paragraph(lines) if lines else ("", bbox)
        )
        text = text.strip()
        if not text and block_type in {"title", "paragraph"}:
            continue

        level = 0
        if block_type == "title":
            # attach words to lines for size detection
            line_with_words = []
            line_words: list[list[dict[str, Any]]] = [[] for _ in lines]
            for w in words:
                # find line
                for i, line in enumerate(lines):
                    if (
                        line["top"] - 2 <= w["top"] <= line["bottom"] + 2
                        and line["x0"] - 2 <= w["x0"] <= line["x1"] + 2
                    ):
                        line_words[i].append(w)
                        break
            for i, lw in enumerate(line_words):
                lines[i]["words"] = lw
            level = _detect_title_level_by_fontsize(lines, page_w)

        # IMPORTANT: use DocLayout's detection bbox, not the text bbox.
        # The text bbox only covers the ink inside, while the detection
        # bbox covers the whole region (and is what NMS/merge needs).
        blocks.append(
            Block(
                type=block_type,
                text=text,
                page=page_no,
                bbox=bbox,
                confidence=float(b.conf),
                level=level,
            )
        )

    # Drop smaller boxes that are mostly inside a larger box of the same type
    blocks = _nms(blocks, iou_thresh=0.5)
    blocks = _merge_adjacent_blocks(blocks)
    # Detect 2-column layout for cross-column merge
    text_blocks_for_detect = [
        b for b in blocks if b.type in ("paragraph", "title")
    ]
    is_2col_local, boundary = _is_two_column(text_blocks_for_detect, page_w)
    # Merge cross-column (left/right) wrapped paragraphs
    if is_2col_local:
        blocks = _merge_cross_column(blocks, boundary)
    # Sort by reading order (1-col vs 2-col aware)
    blocks = _apply_reading_order(blocks, page_w)
    return blocks


def _area(bbox: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _nms(blocks: list[Block], iou_thresh: float = 0.5) -> list[Block]:
    """Remove boxes mostly contained in larger boxes of the same type.

    DocLayout can over-detect: a single paragraph region may produce
    a big outer box plus several inner fragment boxes (one per column).
    We drop the smaller boxes that are mostly inside a larger one.
    """
    if len(blocks) <= 1:
        return blocks
    keep: list[Block] = []
    # Sort by area desc so larger boxes are processed first
    remaining = sorted(blocks, key=lambda b: -_area(b.bbox))
    while remaining:
        big = remaining.pop(0)
        keep.append(big)
        remaining = [
            small
            for small in remaining
            if not _is_mostly_inside(small.bbox, big.bbox)
            or small.type != big.type
        ]
    return keep


def _is_mostly_inside(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    """True if inner is fully inside outer (geometric containment)."""
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    # Strict containment with a small margin to handle float fuzz
    margin = 2.0
    return (
        ix0 >= ox0 - margin
        and iy0 >= oy0 - margin
        and ix1 <= ox1 + margin
        and iy1 <= oy1 + margin
    )


def _is_two_column(
    text_blocks: list[Block], page_w: float
) -> tuple[bool, float]:
    """Heuristic 2-column detection.

    Returns (is_2col, column_boundary_x).
    column_boundary_x is the x where left/right columns split.

    Conditions:
    - At least 4 paragraph blocks
    - x-centers split into 2 clusters with a clear gap (> 4% of page width)
    - each cluster has at least 2 members
    - rightmost cluster center > 0.6 * page_w
    """
    if len(text_blocks) < 4:
        return False, page_w / 2

    centers = sorted(
        (b.bbox[0] + b.bbox[2]) / 2 for b in text_blocks
    )
    # Look for the largest gap
    gaps: list[tuple[float, int]] = []  # (gap_size, index_after_gap)
    for i in range(1, len(centers)):
        gaps.append((centers[i] - centers[i - 1], i))
    gaps.sort(reverse=True)

    gap_size, split_idx = gaps[0]
    if gap_size < page_w * 0.04:
        return False, page_w / 2

    # Both sides must have >= 2 blocks
    if split_idx < 2 or len(centers) - split_idx < 2:
        return False, page_w / 2

    left_center = sum(centers[:split_idx]) / split_idx
    right_center = sum(centers[split_idx:]) / (len(centers) - split_idx)
    boundary = (centers[split_idx - 1] + centers[split_idx]) / 2

    # Sanity: right cluster should be on the right half
    if right_center < page_w * 0.55:
        return False, page_w / 2
    if left_center > page_w * 0.45:
        return False, page_w / 2

    return True, float(boundary)


def _assign_block_to_column(
    b: Block, boundary: float
) -> int:
    """0 for left, 1 for right (based on x-center)."""
    cx = (b.bbox[0] + b.bbox[2]) / 2
    return 0 if cx < boundary else 1


def _reading_order_2col(blocks: list[Block], boundary: float) -> list[Block]:
    """Sort blocks for 2-column reading order.

    Standard academic 2-column layout: read the LEFT column top-to-bottom,
    then the RIGHT column top-to-bottom. Within each column, blocks are
    sorted by their y coordinate.

    Blocks that span the full width (e.g., section headers that span both
    columns on a single-column page, or figures wider than a column) are
    detected and inserted at the appropriate y position.

    The split boundary comes from _is_two_column detection.
    """
    # Identify "spanning" blocks: width >= 70% of page width
    # (these are section headers or wide figures, treat as separate band)
    # For now, put them at their natural y position
    spanning: list[Block] = []
    left: list[Block] = []
    right: list[Block] = []

    for b in blocks:
        w = b.bbox[2] - b.bbox[0]
        cx = (b.bbox[0] + b.bbox[2]) / 2
        if w > 400 and cx < 612:  # 612pt = typical page width; 400 is heuristic
            spanning.append(b)
        elif cx < boundary:
            left.append(b)
        else:
            right.append(b)

    left.sort(key=lambda b: b.bbox[1])
    right.sort(key=lambda b: b.bbox[1])
    spanning.sort(key=lambda b: b.bbox[1])

    # Interleave by y: at any y, if spanning block exists, output it first
    # (headers above this y), then continue with column content.
    result: list[Block] = []

    # Simple approach: output all spanning blocks at their natural y,
    # interleaved with column content
    li, ri, si = 0, 0, 0
    last_y = -1.0

    # We iterate by y-order across all blocks but prefer column order
    # Build a unified queue
    pending = []
    pending.extend(left)
    pending.extend(right)
    pending.extend(spanning)
    pending.sort(key=lambda b: b.bbox[1])

    # But respect column priority: left column block beats right column
    # block at the same y band.
    # Heuristic: for each block, decide if it should "skip" the right column
    # by being pulled forward in the output.

    # Practical implementation: emit left blocks first, then insert right
    # blocks at appropriate positions. The simplest correct approach is
    # to detect when reading switches column: when left column has a gap
    # (no more blocks below current y in left), switch to right column.

    # For now: pure left-then-right (loses interleaving but is correct
    # for most cases)
    for b in left:
        result.append(b)
    for b in right:
        result.append(b)
    for b in spanning:
        # Insert spanning blocks at their natural position
        for i, existing in enumerate(result):
            if existing.bbox[1] > b.bbox[1]:
                result.insert(i, b)
                break
        else:
            result.append(b)

    return result


def _reading_order_1col(blocks: list[Block]) -> list[Block]:
    return sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))


def _apply_reading_order(blocks: list[Block], page_w: float) -> list[Block]:
    """Sort blocks in proper reading order for the page layout.

    Detects 1-col vs 2-col by analyzing paragraph block x-distribution.
    """
    text_blocks = [b for b in blocks if b.type in ("paragraph", "title")]
    is_2col, boundary = _is_two_column(text_blocks, page_w)
    if is_2col:
        return _reading_order_2col(blocks, boundary)
    return _reading_order_1col(blocks)


def _should_merge(b1: Block, b2: Block, y_gap: float = 12.0, x_overlap_min: float = 0.3) -> bool:
    """Heuristic: two adjacent paragraph blocks likely belong to the same paragraph.

    Conditions:
    - Same type
    - y distance is small (within ~12pt = 1.5 line height)
    - x ranges overlap significantly (same column)
    """
    if b1.type != b2.type:
        return False
    if b1.type not in ("paragraph", "title"):
        return False
    _, y1_0, x1_1, _ = b1.bbox
    x1_0, _, _, y1_1 = b1.bbox
    _, y2_0, x2_1, _ = b2.bbox
    x2_0, _, _, y2_1 = b2.bbox
    # y distance: bottom of b1 to top of b2
    y_dist = y2_0 - y1_1
    if y_dist > y_gap or y_dist < -y_gap * 2:
        return False
    # x overlap: how much of the smaller width is shared
    overlap = min(x1_1, x2_1) - max(x1_0, x2_0)
    width = min(x1_1 - x1_0, x2_1 - x2_0)
    if width <= 0:
        return False
    if overlap / width < x_overlap_min:
        return False
    return True


def _y_overlap_ratio(
    b1: Block, b2: Block
) -> float:
    """Vertical overlap ratio between two bboxes (smaller height / larger height)."""
    a_y0, a_y1 = b1.bbox[1], b1.bbox[3]
    b_y0, b_y1 = b2.bbox[1], b2.bbox[3]
    overlap = max(0, min(a_y1, b_y1) - max(a_y0, b_y0))
    smaller = min(a_y1 - a_y0, b_y1 - b_y0)
    larger = max(a_y1 - a_y0, b_y1 - b_y0)
    if larger <= 0:
        return 0.0
    return overlap / larger


def _is_same_paragraph_across_columns(
    left: Block, right: Block, gap_x: float
) -> bool:
    """Heuristic: a left-column block and right-column block belong to the
    same paragraph when:

    1. y-ranges strongly overlap (>= 30% of the smaller block), or
    2. The left block's bottom is close to the right block's top
       (vertical gap 0..8pt) — adjacent blocks in reading order

    DocLayout can fragment a long paragraph into multiple boxes; we don't
    try to recover the "right block is a sliver of the abstract" case
    because that heuristic leads to false positives where DocLayout
    detects a separate intro paragraph as if it were part of the
    abstract (e.g., ResNet page 1).
    """
    if left.type != "paragraph" or right.type != "paragraph":
        return False
    if left.bbox[0] >= right.bbox[0]:
        return False
    # Condition 1: strong y overlap
    if _y_overlap_ratio(left, right) >= 0.3:
        return True
    # Condition 2: small vertical gap (left ends just above right starts)
    left_bottom = left.bbox[3]
    right_top = right.bbox[1]
    if 0 <= (right_top - left_bottom) <= 8:
        return True
    return False


def _merge_cross_column(blocks: list[Block], boundary: float) -> list[Block]:
    """Merge left-column paragraphs that wrap to the right column.

    Algorithm:
    - For each right-column paragraph, look at the left-column paragraph
      whose y-range overlaps it. If they look like the same wrapped
      paragraph, append right's text to left and remove right.
    - The right block's text gets concatenated to left.
    """
    if not blocks:
        return blocks
    # Split by column using cx < boundary
    left = [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 < boundary]
    right = [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 >= boundary]
    left.sort(key=lambda b: b.bbox[1])
    right.sort(key=lambda b: b.bbox[1])

    consumed_right: set[int] = set()
    for li, lb in enumerate(left):
        for ri, rb in enumerate(right):
            if ri in consumed_right:
                continue
            if _is_same_paragraph_across_columns(lb, rb, boundary):
                # join: append right's text (with space) to left
                sep = "" if (lb.text.endswith((" ", "\n", "-")) or not lb.text) else " "
                lb.text = lb.text + sep + rb.text
                # extend bbox to cover both columns
                lb.bbox = (
                    min(lb.bbox[0], rb.bbox[0]),
                    min(lb.bbox[1], rb.bbox[1]),
                    max(lb.bbox[2], rb.bbox[2]),
                    max(lb.bbox[3], rb.bbox[3]),
                )
                consumed_right.add(ri)

    return [b for i, b in enumerate(right) if i not in consumed_right] + left


def _merge_adjacent_blocks(blocks: list[Block]) -> list[Block]:
    """Greedy merge of consecutive blocks that look like the same paragraph."""
    if not blocks:
        return blocks
    merged: list[Block] = [blocks[0]]
    for b in blocks[1:]:
        prev = merged[-1]
        if _should_merge(prev, b):
            # join text and extend bbox
            sep = " " if not prev.text.endswith(("\n", " ")) else ""
            prev.text = prev.text + sep + b.text
            x0 = min(prev.bbox[0], b.bbox[0])
            y0 = min(prev.bbox[1], b.bbox[1])
            x1 = max(prev.bbox[2], b.bbox[2])
            y1 = max(prev.bbox[3], b.bbox[3])
            prev.bbox = (x0, y0, x1, y1)
            prev.confidence = min(prev.confidence, b.confidence)
        else:
            merged.append(b)
    return merged


def extract_blocks(pdf_path: str | Path) -> list[Block]:
    """Extract structured blocks from a PDF.

    Returns blocks in reading order: top-to-bottom, left-to-right.
    Skips headers/footers/decorations (DocLayout 'abandon' class).
    """
    import fitz  # pymupdf
    import pdfplumber

    t0 = time.time()
    pdf_path = str(pdf_path)
    pymu_doc = fitz.open(pdf_path)
    blocks: list[Block] = []
    try:
        with pdfplumber.open(pdf_path) as plumber_pdf:
            total = len(pymu_doc)
            for i in range(total):
                blocks.extend(_process_page(i, pymu_doc, plumber_pdf))
    finally:
        pymu_doc.close()
    logger.info(
        "blocks.extracted",
        path=pdf_path,
        count=len(blocks),
        elapsed=round(time.time() - t0, 2),
    )
    return blocks


async def extract_blocks_async(pdf_path: str | Path) -> list[Block]:
    """Async wrapper for extract_blocks (CPU bound, run in thread)."""
    import asyncio

    return await asyncio.to_thread(extract_blocks, pdf_path)


# ─────────────────────────────────────────────────────────────────────
# Markdown / DOCX rendering (stubs for now, full impl in steps C/D)
# ─────────────────────────────────────────────────────────────────────


import re

# Section numbering patterns for smart title level detection
_RE_SECTION_1 = re.compile(r"^\s*(\d+)[\.\s]")
_RE_SECTION_2 = re.compile(r"^\s*(\d+)\.(\d+)[\.\s]")
_RE_SECTION_3 = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)[\.\s]")
_RE_SECTION_4 = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)\.(\d+)[\.\s]")
_RE_ABSTRACT = re.compile(r"^\s*abstract\b", re.IGNORECASE)
_RE_REFERENCES = re.compile(r"^\s*references\b", re.IGNORECASE)
_RE_ACK = re.compile(r"^\s*(acknowledg(e)?ments?|acknowledge(ment)?)\b", re.IGNORECASE)
_RE_APPENDIX = re.compile(r"^\s*appendix\b", re.IGNORECASE)


def _detect_title_level(text: str) -> int | None:
    """Detect markdown header level from title text.

    Returns 1..6 for headers, None if not a clear title.
    - 'Abstract' / 'References' / 'Acknowledgments' -> level 1
    - '1', '2' (no dot) -> level 1
    - '1.1', '1.2' -> level 2
    - '1.1.1' -> level 3
    - 'A.1', 'Appendix A' -> level 1
    """
    if not text:
        return None
    t = text.strip()
    if not t:
        return None
    # Look for the section number at the start, possibly followed by title
    if _RE_SECTION_4.match(t):
        return 4
    if _RE_SECTION_3.match(t):
        return 3
    if _RE_SECTION_2.match(t):
        return 2
    if _RE_SECTION_1.match(t):
        return 1
    if _RE_ABSTRACT.match(t) or _RE_REFERENCES.match(t) or _RE_ACK.match(t) or _RE_APPENDIX.match(t):
        return 1
    return None


def _clean_title_text(text: str) -> str:
    """Strip leading section numbers and clean up title text.

    '1. Introduction' -> 'Introduction'
    '3.2.1 Scaled Dot-Product' -> '3.2.1 Scaled Dot-Product' (keep 1.1.1 prefix)
    """
    t = text.strip()
    # Remove leading "1.1.1 " or "1.1 " or "1 " (with or without dot) when followed by Title-case word
    # but keep "1.1.1" since it's a real sub-section number
    m = re.match(r"^\s*(\d+(?:\.\d+){0,3})[\.\s]+([A-Z].*)$", t)
    if m:
        sec, rest = m.group(1), m.group(2)
        # If the section number is "1" or "2" etc. (no sub-dots), drop it
        if "." not in sec:
            return rest
        return f"{sec} {rest}"
    return t


def _is_equation_number(text: str) -> bool:
    """Detect a standalone equation number like '(1)' or '(12)'."""
    return bool(re.match(r"^\s*\((\d+)\)\s*$", text.strip()))


def _block_to_markdown(b: Block, *, include_figures: bool) -> list[str]:
    """Render a single block to a list of markdown lines (without trailing blank lines)."""
    if b.type == "title":
        # Smart level detection: prefer regex over detected level
        smart = _detect_title_level(b.text)
        level = smart if smart is not None else (b.level if b.level > 0 else 2)
        # Clamp to 1..6
        level = max(1, min(6, level))
        prefix = "#" * level
        cleaned = _clean_title_text(b.text)
        return [f"{prefix} {cleaned}"]
    if b.type == "paragraph":
        if not b.text:
            return []
        return [b.text]
    if b.type == "table":
        # Render table as GFM placeholder; the real table extraction
        # happens in step D using pdfplumber.extract_tables on the bbox.
        if not b.text:
            return ["<!-- table -->"]
        # Try to format as GFM if it looks like "Col1 Col2\nval1 val2"
        return [f"<!-- table -->\n{b.text}"]
    if b.type == "table_caption":
        if not b.text:
            return []
        return [f"*{b.text}*"]
    if b.type == "formula":
        if _is_equation_number(b.text):
            return []  # skip standalone equation numbers, will be merged into the previous formula
        if not b.text or b.text.strip() in ("", "[公式: 略]"):
            return ["$$\n\\text{[公式: 略]}\n$$"]
        return [f"$$\n{b.text.strip()}\n$$"]
    if b.type == "figure":
        if not include_figures:
            return []
        return [f"![figure](空) {b.text}".strip()] if b.text else ["![figure](空)"]
    if b.type == "figure_caption":
        if not b.text:
            return []
        return [f"*{b.text}*"]
    if b.text:
        return [b.text]
    return []


def _merge_equation_numbers(blocks: list[Block]) -> list[Block]:
    """Merge a standalone equation number (e.g. '(1)') into the previous
    formula block, so we don't get a dangling '(1)' on its own line."""
    out: list[Block] = []
    for b in blocks:
        if b.type == "formula" and _is_equation_number(b.text):
            # Find the previous formula block and append "(N)" to its text
            for j in range(len(out) - 1, -1, -1):
                if out[j].type == "formula":
                    out[j].text = f"{out[j].text.rstrip()} {b.text.strip()}"
                    break
            # Either way, don't add the standalone number block itself
            continue
        out.append(b)
    return out


def _merge_caption_into_figure(blocks: list[Block]) -> list[Block]:
    """Attach a figure_caption to its preceding figure block as a separate
    paragraph (italic), so the caption reads as part of the figure."""
    if not blocks:
        return blocks
    out: list[Block] = []
    for b in blocks:
        if b.type == "figure_caption" and out and out[-1].type == "figure":
            fig = out[-1]
            # store caption as a virtual paragraph in the figure's bbox extension
            if b.text:
                # append a synthetic paragraph after the figure
                caption_block = Block(
                    type="figure_caption",
                    text=b.text,
                    page=b.page,
                    bbox=b.bbox,
                    confidence=b.confidence,
                    lang=b.lang,
                )
                out.append(caption_block)
            continue
        out.append(b)
    return out


def render_markdown(
    blocks: list[Block],
    *,
    include_figures: bool = False,
) -> str:
    """Render blocks to markdown with smart title levels, equation numbers,
    and inter-block spacing.

    Pipeline:
    1. Merge equation numbers into preceding formula
    2. Convert each block to markdown lines
    3. Join blocks with blank lines
    4. Smart title level detection (1, 1.1, 1.1.1, Abstract, ...)
    """
    blocks = _merge_equation_numbers(blocks)
    blocks = _merge_caption_into_figure(blocks)

    chunks: list[str] = []
    for b in blocks:
        lines = _block_to_markdown(b, include_figures=include_figures)
        if lines:
            chunks.append("\n".join(lines))

    return "\n\n".join(chunks).strip()


__all__ = [
    "Block",
    "BlockType",
    "extract_blocks",
    "extract_blocks_async",
    "render_markdown",
]
