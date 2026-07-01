from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging import get_logger
from app.services.llm_service import ainvoke_for_section_detection


logger = get_logger(__name__)


SKIP_SECTION_KEYWORDS = (
    "reference",
    "references",
    "bibliography",
    "acknowledg",
    "acknowledgment",
    "acknowledgement",
    "致谢",
    "参考文献",
)


KEEP_SECTION_KEYWORDS = (
    "abstract",
    "introduction",
    "background",
    "related work",
    "method",
    "methods",
    "methodology",
    "approach",
    "experiment",
    "experiments",
    "result",
    "results",
    "evaluation",
    "discussion",
    "conclusion",
    "conclusions",
    "appendix",
    "supplementary",
    "摘要",
    "引言",
    "介绍",
    "方法",
    "实验",
    "结果",
    "讨论",
    "结论",
    "附录",
)


_HEURISTIC_PATTERNS = [
    (re.compile(r"^\s*abstract\b", re.IGNORECASE | re.MULTILINE), "Abstract"),
    (re.compile(r"^\s*introduction\b", re.IGNORECASE | re.MULTILINE), "Introduction"),
    (re.compile(r"^\s*(related\s+work|background)\b", re.IGNORECASE | re.MULTILINE), "Related Work"),
    (re.compile(r"^\s*method(s|ology)?\b", re.IGNORECASE | re.MULTILINE), "Methods"),
    (re.compile(r"^\s*experiment(s|al)?\b", re.IGNORECASE | re.MULTILINE), "Experiments"),
    (re.compile(r"^\s*result(s)?\b", re.IGNORECASE | re.MULTILINE), "Results"),
    (re.compile(r"^\s*discussion\b", re.IGNORECASE | re.MULTILINE), "Discussion"),
    (re.compile(r"^\s*conclusion(s)?\b", re.IGNORECASE | re.MULTILINE), "Conclusions"),
    (re.compile(r"^\s*reference(s|\s+list)?\b", re.IGNORECASE | re.MULTILINE), "References"),
    (re.compile(r"^\s*acknowledg(e)?ment(s)?\b", re.IGNORECASE | re.MULTILINE), "Acknowledgments"),
    (re.compile(r"^\s*bibliography\b", re.IGNORECASE | re.MULTILINE), "Bibliography"),
    (re.compile(r"^\s*appendix\b", re.IGNORECASE | re.MULTILINE), "Appendix"),
]


def should_translate_section(section_name: str) -> bool:
    if not section_name:
        return True
    name = section_name.strip().lower()
    for kw in SKIP_SECTION_KEYWORDS:
        if kw in name:
            return False
    return True


def detect_sections_heuristic(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    if not text:
        return sections
    lines = text.splitlines()
    current_name = "Header"
    current_lines: list[str] = []
    buckets: dict[str, list[str]] = {}

    def _flush() -> None:
        if current_lines:
            buckets.setdefault(current_name, []).extend(current_lines)

    for line in lines:
        matched = False
        for pattern, label in _HEURISTIC_PATTERNS:
            if pattern.match(line):
                _flush()
                current_name = label
                current_lines = []
                matched = True
                break
        if not matched:
            current_lines.append(line)
    _flush()
    for name, body_lines in buckets.items():
        joined = "\n".join(body_lines).strip()
        if joined:
            sections[name] = joined[:20000]
    return sections


async def detect_sections(text: str, *, use_llm: bool = True) -> dict[str, str]:
    heuristic = detect_sections_heuristic(text)
    if not use_llm or not heuristic:
        return heuristic
    try:
        excerpt = text[:6000]
        raw = await ainvoke_for_section_detection(excerpt)
        content = raw.get("translation") or raw.get("content") or ""
        parsed = _parse_section_response(content)
        if parsed:
            merged: dict[str, str] = {}
            for sec in parsed:
                name = sec.get("name") or "Unknown"
                if sec.get("translate", True) and should_translate_section(name):
                    body = heuristic.get(name) or ""
                    if body:
                        merged[name] = body
                else:
                    continue
            for name, body in heuristic.items():
                if should_translate_section(name) and name not in merged:
                    merged[name] = body
            return merged
    except Exception as exc:
        logger.warning(
            "structure.detect_sections.llm_failed",
            error=str(exc),
        )
    return {k: v for k, v in heuristic.items() if should_translate_section(k)}


def _parse_section_response(content: str) -> list[dict[str, Any]]:
    if not content:
        return []
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, count=1).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "sections" in parsed:
            parsed = parsed["sections"]
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, dict)]
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return [p for p in parsed if isinstance(p, dict)]
            except json.JSONDecodeError:
                return []
    return []


def inject_glossary_into_prompt(glossary: list[dict[str, Any]]) -> str:
    if not glossary:
        return ""
    lines = ["必须按下列术语对照表翻译（原文 -> 译文）："]
    for entry in glossary:
        if not isinstance(entry, dict):
            continue
        term = entry.get("term") or entry.get("source")
        translation = entry.get("translation") or entry.get("target")
        if not term or not translation:
            continue
        ctx = entry.get("context")
        suffix = f" ({ctx})" if ctx else ""
        lines.append(f"- {term} -> {translation}{suffix}")
    return "\n".join(lines)


def build_skip_references_prompt(skip: bool = True) -> str:
    if not skip:
        return ""
    return (
        "Don't translate References / Bibliography / Acknowledgments sections; "
        "preserve DOI, author names, and years as-is. Keep citations and footnotes unchanged."
    )


__all__ = [
    "should_translate_section",
    "detect_sections_heuristic",
    "detect_sections",
    "inject_glossary_into_prompt",
    "build_skip_references_prompt",
]