#!/usr/bin/env python3
"""Download a curated arXiv benchmark set for PDF translation evaluation."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

PAPERS = [
    # CS/AI with formulas and pseudocode
    {
        "name": "attention_is_all_you_need",
        "arxiv_id": "1706.03762",
        "category": "CS/AI",
        "title": "Attention Is All You Need",
    },
    {
        "name": "bert",
        "arxiv_id": "1810.04805",
        "category": "CS/AI",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
    },
    # CV / Remote sensing
    {
        "name": "changeformer",
        "arxiv_id": "2201.01293",
        "category": "CV/Remote Sensing",
        "title": "ChangeFormer: A Transformer-Based Change Detection Model",
    },
    {
        "name": "segment_anything",
        "arxiv_id": "2304.02643",
        "category": "CV/Remote Sensing",
        "title": "Segment Anything",
    },
    # Biomedical
    {
        "name": "biobert",
        "arxiv_id": "1901.08746",
        "category": "Biomedical",
        "title": "BioBERT: a pre-trained biomedical language representation model",
    },
    {
        "name": "pubmedbert",
        "arxiv_id": "2007.15779",
        "category": "Biomedical",
        "title": "Domain-Specific Language Model Pretraining for Biomedical NLP",
    },
    # Math / Optimization
    {
        "name": "adam",
        "arxiv_id": "1412.6980",
        "category": "Math/Optimization",
        "title": "Adam: A Method for Stochastic Optimization",
    },
    {
        "name": "adam_convergence",
        "arxiv_id": "1904.09237",
        "category": "Math/Optimization",
        "title": "On the Convergence of Adam and Beyond",
    },
    # Short paper
    {
        "name": "distilling_knowledge",
        "arxiv_id": "1503.02531",
        "category": "Short paper",
        "title": "Distilling the Knowledge in a Neural Network",
    },
    # Long survey
    {
        "name": "llm_survey",
        "arxiv_id": "2303.18223",
        "category": "Long survey",
        "title": "A Survey on Large Language Models",
    },
]


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "paper-translate-benchmark/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def main() -> None:
    papers_dir = Path(__file__).parent / "data" / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for paper in PAPERS:
        dest = papers_dir / f"{paper['name']}.pdf"
        url = f"https://arxiv.org/pdf/{paper['arxiv_id']}.pdf"
        print(f"Downloading {paper['name']} ({paper['arxiv_id']})...")
        try:
            download(url, dest)
            size_kb = dest.stat().st_size / 1024
            print(f"  -> {dest.name} ({size_kb:.1f} KB)")
            manifest.append(
                {
                    **paper,
                    "file": dest.name,
                    "size_kb": round(size_kb, 1),
                    "status": "ok",
                }
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}")
            manifest.append({**paper, "file": dest.name, "status": "failed", "error": str(exc)})
        time.sleep(2)

    manifest_path = papers_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nManifest written to {manifest_path}")


if __name__ == "__main__":
    main()
