#!/usr/bin/env python3
"""Evaluate saved ESASR predictions against a JSONL gold set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.metrics import evaluate_cutoffs


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
        description=(
            "Compute retrieval/ranking quality, bootstrap intervals, query constraints, "
            "structured-output coverage, and optional Token/API/latency statistics."
        ),
    )
    parser.add_argument("--gold", required=True, type=Path, help="Gold JSONL benchmark")
    parser.add_argument("--predictions", required=True, type=Path, help="Prediction JSONL")
    parser.add_argument(
        "--k",
        type=int,
        action="append",
        help="Evaluate the first K results; repeat for multiple cutoffs (default: 20)",
    )
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, help="Optional detailed JSON report")
    args = parser.parse_args()
    cutoffs = args.k or [20]
    if min(cutoffs) < 1:
        parser.error("--k must be at least 1")
    if args.bootstrap_samples < 0:
        parser.error("--bootstrap-samples cannot be negative")
    if not 0 < args.confidence < 1:
        parser.error("--confidence must be between 0 and 1")

    gold_rows = read_jsonl(args.gold)
    prediction_rows = read_jsonl(args.predictions)
    reports = evaluate_cutoffs(
        gold_rows,
        prediction_rows,
        cutoffs,
        bootstrap_samples=args.bootstrap_samples,
        confidence=args.confidence,
        seed=args.seed,
    )
    report = reports[str(cutoffs[0])] if len(set(cutoffs)) == 1 else {"cutoffs": reports}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    for k in sorted(reports, key=int):
        cutoff_report = reports[k]
        macro = cutoff_report["macro"]
        micro = cutoff_report["micro"]
        interval = cutoff_report["macroConfidenceIntervals"]["f1"]
        print(
            f"queries={cutoff_report['queries']} k={k} "
            f"macro(P/R/F1)={macro['precision']:.4f}/{macro['recall']:.4f}/{macro['f1']:.4f} "
            f"F1-CI=[{interval['low']:.4f},{interval['high']:.4f}] "
            f"MAP/MRR/nDCG={macro['averagePrecision']:.4f}/"
            f"{macro['reciprocalRank']:.4f}/{macro['ndcg']:.4f} "
            f"micro(P/R/F1)={micro['precision']:.4f}/{micro['recall']:.4f}/{micro['f1']:.4f}"
        )
        if cutoff_report["missingPredictions"]:
            print(
                f"missing predictions: {', '.join(cutoff_report['missingPredictions'])}",
                file=sys.stderr,
            )
        if cutoff_report["duplicatePredictionIds"]:
            print(
                f"duplicate prediction ids: {', '.join(cutoff_report['duplicatePredictionIds'])}",
                file=sys.stderr,
            )
        if cutoff_report["extraPredictionIds"]:
            print(
                f"prediction ids absent from gold: {', '.join(cutoff_report['extraPredictionIds'])}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
