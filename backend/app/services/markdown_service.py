from __future__ import annotations

import asyncio
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.logging import get_logger


logger = get_logger(__name__)


_PDF_TEXT_BLOCK_SEP = "\n\n"


def _extract_text_with_pdfplumber(pdf_path: str | Path) -> list[dict[str, Any]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber not installed") from exc
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": idx, "text": text})
    return pages


def _extract_text_with_pymupdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pymupdf not installed") from exc
    pages: list[dict[str, Any]] = []
    with fitz.open(str(pdf_path)) as doc:
        for idx, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append({"page": idx, "text": text})
    return pages


def _extract_text_fallback(pdf_path: str | Path) -> list[dict[str, Any]]:
    last_err: Exception | None = None
    for fn in (_extract_text_with_pdfplumber, _extract_text_with_pymupdf):
        try:
            return fn(pdf_path)
        except Exception as exc:
            last_err = exc
            logger.warning(
                "markdown.extract.fallback",
                extractor=fn.__name__,
                error=str(exc),
            )
            continue
    raise RuntimeError(f"failed to extract text from PDF: {last_err}")


def _pages_to_markdown(pages: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for entry in pages:
        page_no = entry.get("page")
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        cleaned = _normalize_text(text)
        chunks.append(f"## Page {page_no}\n\n{cleaned}")
    return "\n\n".join(chunks).strip()


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def convert_pdf_to_markdown(
    pdf_path: str | Path,
    *,
    use_pandoc: bool = True,
) -> str:
    def _run_pandoc() -> str:
        try:
            import pypandoc
        except ImportError as exc:
            raise RuntimeError("pypandoc not installed") from exc
        try:
            return pypandoc.convert_file(
                str(pdf_path),
                "md",
                format="pdf",
                extra_args=["--standalone"],
            )
        except Exception as exc:
            raise RuntimeError(f"pypandoc conversion failed: {exc}") from exc

    if use_pandoc:
        try:
            return await asyncio.to_thread(_run_pandoc)
        except Exception as exc:
            logger.warning(
                "markdown.pandoc_failed",
                error=str(exc),
                fallback="pdfplumber",
            )
    pages = await asyncio.to_thread(_extract_text_fallback, pdf_path)
    return _pages_to_markdown(pages)


async def convert_pdf_to_docx(
    pdf_path: str | Path,
    *,
    use_pandoc: bool = True,
) -> bytes:
    def _run_pandoc() -> bytes:
        try:
            import pypandoc
        except ImportError as exc:
            raise RuntimeError("pypandoc not installed") from exc
        try:
            buffer = BytesIO()
            pypandoc.convert_file(
                str(pdf_path),
                "docx",
                format="pdf",
                outputfile=buffer,
                extra_args=["--standalone"],
            )
            return buffer.getvalue()
        except Exception as exc:
            raise RuntimeError(f"pypandoc docx conversion failed: {exc}") from exc

    if use_pandoc:
        try:
            return await asyncio.to_thread(_run_pandoc)
        except Exception as exc:
            logger.warning(
                "markdown.docx_pandoc_failed",
                error=str(exc),
                fallback="text",
            )
    pages = await asyncio.to_thread(_extract_text_fallback, pdf_path)
    text = _pages_to_markdown(pages)

    def _make_text_docx() -> bytes:
        try:
            from docx import Document
        except ImportError:
            return text.encode("utf-8")
        doc = Document()
        for line in text.splitlines():
            doc.add_paragraph(line)
        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()

    return await asyncio.to_thread(_make_text_docx)


async def extract_pages_text(pdf_path: str | Path) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_extract_text_fallback, pdf_path)


__all__ = [
    "convert_pdf_to_markdown",
    "convert_pdf_to_docx",
    "extract_pages_text",
]