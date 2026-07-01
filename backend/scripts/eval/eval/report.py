"""Generate HTML/CSV reports from benchmark results."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.metrics import PaperMetrics


_HTML_TEMPLATE = """\
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>论文翻译模型评测报告</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    .best {{ background: #e6ffed; font-weight: bold; }}
  </style>
</head>
<body>
  <h1>论文翻译模型评测报告</h1>
  <p>生成时间：{generated_at}</p>
  {summary_html}
  {table_html}
</body>
</html>
"""


def _build_summary(metrics: list[PaperMetrics]) -> str:
    from collections import defaultdict

    grouped: dict[tuple[str, str], list[PaperMetrics]] = defaultdict(list)
    for m in metrics:
        grouped[(m.service, m.model)].append(m)

    rows = []
    for (service, model), items in sorted(grouped.items()):
        total_cost = sum(i.total_cost_cny for i in items)
        total_latency = sum(i.total_latency_ms for i in items)
        total_blocks = sum(i.total_blocks for i in items)
        term_total = sum(i.term_total for i in items)
        term_violations = sum(i.term_violations for i in items)
        eq_total = sum(i.equation_refs_total for i in items)
        eq_preserved = sum(i.equation_refs_preserved for i in items)
        fig_total = sum(i.figure_refs_total for i in items)
        fig_preserved = sum(i.figure_refs_preserved for i in items)

        term_rate = (1 - term_violations / term_total) * 100 if term_total else 0
        eq_rate = (eq_preserved / eq_total) * 100 if eq_total else 0
        fig_rate = (fig_preserved / fig_total) * 100 if fig_total else 0
        avg_latency_per_block = total_latency / total_blocks if total_blocks else 0

        rows.append(
            f"""
            <tr>
              <td>{service}</td>
              <td>{model}</td>
              <td>{total_cost:.4f}</td>
              <td>{avg_latency_per_block:.0f} ms</td>
              <td>{term_rate:.1f}%</td>
              <td>{eq_rate:.1f}%</td>
              <td>{fig_rate:.1f}%</td>
            </tr>
            """
        )

    return (
        "<h2>汇总</h2>"
        "<table>"
        "<tr><th>服务</th><th>模型</th>"
        "<th>总成本(CNY)</th><th>平均块耗时</th>"
        "<th>术语一致率</th><th>公式编号保留率</th>"
        "<th>图表引用保留率</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _build_detail_table(metrics: list[PaperMetrics]) -> str:
    rows = []
    for m in metrics:
        term_rate = (1 - m.term_violations / m.term_total) * 100 if m.term_total else 0
        eq_rate = (m.equation_refs_preserved / m.equation_refs_total) * 100 if m.equation_refs_total else 0
        fig_rate = (m.figure_refs_preserved / m.figure_refs_total) * 100 if m.figure_refs_total else 0
        rows.append(
            f"""
            <tr>
              <td>{m.service}</td>
              <td>{m.model}</td>
              <td>{m.paper_id}</td>
              <td>{m.total_blocks}</td>
              <td>{m.total_cost_cny:.6f}</td>
              <td>{m.total_latency_ms:.0f}</td>
              <td>{term_rate:.1f}%</td>
              <td>{eq_rate:.1f}%</td>
              <td>{fig_rate:.1f}%</td>
            </tr>
            """
        )
    return (
        "<h2>明细</h2>"
        "<table>"
        "<tr><th>服务</th><th>模型</th><th>论文</th>"
        "<th>块数</th><th>成本</th><th>耗时(ms)</th>"
        "<th>术语一致率</th><th>公式保留率</th><th>图表保留率</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def write_html_report(metrics: list[PaperMetrics], path: Path) -> None:
    from datetime import datetime, timezone

    summary_html = _build_summary(metrics)
    table_html = _build_detail_table(metrics)
    html = _HTML_TEMPLATE.format(
        generated_at=datetime.now(timezone.utc).isoformat(),
        summary_html=summary_html,
        table_html=table_html,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def write_csv_report(metrics: list[PaperMetrics], path: Path) -> None:
    from eval.metrics import format_metric_report

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_metric_report(metrics), encoding="utf-8")
