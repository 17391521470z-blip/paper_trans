"""主入口：对指定 PDF 样本集跑多模型翻译评测."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Allow importing backend app modules from scripts/eval
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.logging import get_logger

from eval.dataset import (
    discover_papers,
    filter_translatable_blocks,
    load_or_extract_blocks,
)
from eval.metrics import aggregate_paper_metrics
from eval.models import (
    load_model_configs,
    save_results,
    translate_paper_blocks,
    ModelConfig,
)
from eval.report import write_csv_report, write_html_report


logger = get_logger("benchmark")


DEFAULT_PAPERS_DIR = Path(__file__).parent / "data" / "papers"
DEFAULT_BLOCKS_DIR = Path(__file__).parent / "data" / "blocks"
DEFAULT_TRANSLATIONS_DIR = Path(__file__).parent / "data" / "translations"
DEFAULT_REPORTS_DIR = Path(__file__).parent / "data" / "reports"
DEFAULT_MODELS_CONFIG = Path(__file__).parent / "models.json"


def build_glossary_prompt(term_map: dict[str, str]) -> str:
    if not term_map:
        return ""
    lines = ["请使用以下术语对照表（术语必须严格按下表翻译，禁止替换或意译）："]
    for term, translation in term_map.items():
        lines.append(f'- "{term}" → "{translation}"')
    return "\n".join(lines)


def load_term_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["term"]: item["translation"] for item in data if item.get("term")}


async def run_benchmark(
    papers_dir: Path = DEFAULT_PAPERS_DIR,
    models: list[ModelConfig] | None = None,
    term_map: dict[str, str] | None = None,
) -> list:
    papers = discover_papers(papers_dir)
    if not papers:
        raise RuntimeError(f"no PDFs found in {papers_dir}")

    if not models:
        raise RuntimeError("no models configured")

    glossary_prompt = build_glossary_prompt(term_map or {})

    all_metrics = []
    for pdf_path in papers:
        paper_id = pdf_path.stem
        logger.info("benchmark.paper", paper_id=paper_id)
        blocks = load_or_extract_blocks(pdf_path, DEFAULT_BLOCKS_DIR)
        translatable = filter_translatable_blocks(blocks)

        for cfg in models:
            logger.info(
                "benchmark.run",
                paper_id=paper_id,
                model=cfg.name,
                api_model=cfg.model,
            )
            results = await translate_paper_blocks(
                paper_id,
                translatable,
                cfg,
                glossary_prompt,
            )
            save_results(
                results,
                DEFAULT_TRANSLATIONS_DIR / f"{paper_id}_{cfg.name}.json",
            )
            metrics = aggregate_paper_metrics(paper_id, results, term_map or {})
            all_metrics.append(metrics)

    return all_metrics


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run paper translation benchmark")
    parser.add_argument(
        "--papers-dir",
        type=Path,
        default=DEFAULT_PAPERS_DIR,
        help="Directory containing benchmark PDFs",
    )
    parser.add_argument(
        "--terms",
        type=Path,
        default=None,
        help="JSON file with glossary terms [{term, translation}]",
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=DEFAULT_MODELS_CONFIG,
        help="Path to models.json config",
    )
    parser.add_argument(
        "--model-names",
        type=str,
        default=None,
        help="Comma-separated list of model names to run (subset of models.json)",
    )
    args = parser.parse_args()

    if not args.models.exists():
        raise SystemExit(f"models config not found: {args.models}")

    term_map = load_term_map(args.terms)
    all_models = load_model_configs(args.models)

    if args.model_names:
        wanted = {s.strip() for s in args.model_names.split(",")}
        models = [m for m in all_models if m.name in wanted]
        if not models:
            raise SystemExit("no matching models found")
    else:
        models = all_models

    metrics = asyncio.run(run_benchmark(args.papers_dir, models, term_map))

    csv_path = DEFAULT_REPORTS_DIR / "benchmark.csv"
    html_path = DEFAULT_REPORTS_DIR / "benchmark.html"
    write_csv_report(metrics, csv_path)
    write_html_report(metrics, html_path)

    print("Benchmark complete.")
    print(f"  CSV:  {csv_path}")
    print(f"  HTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
