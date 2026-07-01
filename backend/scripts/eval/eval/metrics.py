"""Quality and cost metrics for model evaluation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from eval.models import ModelResult


@dataclass(slots=True)
class PaperMetrics:
    service: str
    model: str
    paper_id: str
    total_blocks: int
    total_cost_cny: float
    total_latency_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    term_violations: int
    term_total: int
    equation_refs_preserved: int
    equation_refs_total: int
    figure_refs_preserved: int
    figure_refs_total: int
    comet_score: float | None = None
    bleu_score: float | None = None


_TERM_PATTERN = re.compile(r"\b([A-Za-z][A-Za-z0-9\s\-/]{0,30}?)\b")


def check_term_consistency(
    results: list[ModelResult],
    term_map: dict[str, str],
) -> tuple[int, int]:
    """Check whether translations respect the glossary term map.

    Returns (violation_count, total_checked).
    """
    violations = 0
    total = 0
    for r in results:
        source = r.source_text
        translation = r.translation
        for term, expected in term_map.items():
            if term.lower() in source.lower():
                total += 1
                if expected not in translation:
                    violations += 1
    return violations, total


_EQUATION_REF_RE = re.compile(r"\(\s*\d+\s*\)")
_FIGURE_REF_RE = re.compile(r"\b(Fig\.?|Figure|Table|Tbl\.?)\s*\d+\b", re.IGNORECASE)


def check_reference_preservation(
    results: list[ModelResult],
) -> dict[str, tuple[int, int]]:
    """Count how many equation/figure/table references are preserved."""
    eq_preserved = eq_total = 0
    fig_preserved = fig_total = 0
    for r in results:
        source_eqs = set(_EQUATION_REF_RE.findall(r.source_text))
        trans_eqs = set(_EQUATION_REF_RE.findall(r.translation))
        eq_total += len(source_eqs)
        eq_preserved += len(source_eqs & trans_eqs)

        source_figs = set(_FIGURE_REF_RE.findall(r.source_text))
        trans_figs = set(_FIGURE_REF_RE.findall(r.translation))
        fig_total += len(source_figs)
        fig_preserved += len(source_figs & trans_figs)
    return {
        "equation": (eq_preserved, eq_total),
        "figure_table": (fig_preserved, fig_total),
    }


def aggregate_paper_metrics(
    paper_id: str,
    results: list[ModelResult],
    term_map: dict[str, str] | None = None,
) -> PaperMetrics:
    """Aggregate metrics for one paper and one model."""
    if not results:
        raise ValueError("empty results")

    service = results[0].service
    model = results[0].model

    term_violations, term_total = check_term_consistency(results, term_map or {})
    ref_counts = check_reference_preservation(results)

    return PaperMetrics(
        service=service,
        model=model,
        paper_id=paper_id,
        total_blocks=len(results),
        total_cost_cny=sum(r.cost_cny for r in results),
        total_latency_ms=sum(r.latency_ms for r in results),
        total_prompt_tokens=sum(r.prompt_tokens for r in results),
        total_completion_tokens=sum(r.completion_tokens for r in results),
        term_violations=term_violations,
        term_total=term_total,
        equation_refs_preserved=ref_counts["equation"][0],
        equation_refs_total=ref_counts["equation"][1],
        figure_refs_preserved=ref_counts["figure_table"][0],
        figure_refs_total=ref_counts["figure_table"][1],
    )


def format_metric_report(metrics: list[PaperMetrics]) -> str:
    lines = [
        "service,model,paper_id,blocks,cost_cny,latency_ms,prompt_tokens,completion_tokens,"
        "term_violations,term_total,equation_refs_preserved,equation_refs_total,"
        "figure_refs_preserved,figure_refs_total",
    ]
    for m in metrics:
        lines.append(
            f"{m.service},{m.model},{m.paper_id},{m.total_blocks},"
            f"{m.total_cost_cny:.6f},{m.total_latency_ms:.2f},"
            f"{m.total_prompt_tokens},{m.total_completion_tokens},"
            f"{m.term_violations},{m.term_total},"
            f"{m.equation_refs_preserved},{m.equation_refs_total},"
            f"{m.figure_refs_preserved},{m.figure_refs_total}"
        )
    return "\n".join(lines)


def try_comet_score(
    predictions: list[str],
    references: list[str],
) -> float | None:
    """Optional COMET score; returns None if package not installed."""
    try:
        from comet import download_model, load_from_checkpoint  # type: ignore
    except ImportError:
        return None

    model_path = download_model("Unbabel/wmt22-comet-da")
    model = load_from_checkpoint(model_path)
    data = [
        {"src": "", "mt": pred, "ref": ref}
        for pred, ref in zip(predictions, references)
    ]
    output = model.predict(data, batch_size=8)
    return float(output.system_score)
