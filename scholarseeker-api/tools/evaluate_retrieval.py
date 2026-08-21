#!/usr/bin/env python3
"""Evaluate saved ScholarSeeker predictions against a JSONL gold set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.metrics import evaluate_dataset


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: each JSONL row must be an object")
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute macro/micro Precision@K, Recall@K and F1@K.",
    )
    parser.add_argument("--gold", required=True, type=Path, help="Gold JSONL benchmark")
    parser.add_argument("--predictions", required=True, type=Path, help="Prediction JSONL")
    parser.add_argument("--k", type=int, default=20, help="Evaluate the first K results")
    parser.add_argument("--out", type=Path, help="Optional detailed JSON report")
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be at least 1")

    report = evaluate_dataset(
        read_jsonl(args.gold),
        read_jsonl(args.predictions),
        args.k,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    macro = report["macro"]
    micro = report["micro"]
    print(
        f"queries={report['queries']} k={report['k']} "
        f"macro(P/R/F1)={macro['precision']:.4f}/{macro['recall']:.4f}/{macro['f1']:.4f} "
        f"micro(P/R/F1)={micro['precision']:.4f}/{micro['recall']:.4f}/{micro['f1']:.4f}"
    )
    if report["missingPredictions"]:
        print(
            f"missing predictions: {', '.join(report['missingPredictions'])}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
