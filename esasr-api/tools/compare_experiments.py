#!/usr/bin/env python3
"""Compare ESASR ablations under a shared retrieval budget."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.metrics import evaluate_cutoffs, paired_bootstrap_delta


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


def parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run must use NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("--run must use non-empty NAME=PATH")
    return name.strip(), Path(raw_path)


def efficiency_mean(report: dict, name: str) -> float | None:
    value = report.get("efficiency", {}).get(name, {}).get("mean")
    return float(value) if isinstance(value, (int, float)) else None


def budget_comparison(baseline: dict, candidate: dict, tolerance: float) -> dict:
    ratios: dict[str, float] = {}
    for name in ("apiCalls", "llmTokens"):
        base = efficiency_mean(baseline, name)
        current = efficiency_mean(candidate, name)
        if base is not None and current is not None and base > 0:
            ratios[name] = round(current / base, 6)
    comparable = all(ratio <= 1 + tolerance for ratio in ratios.values()) if ratios else None
    return {"comparable": comparable, "tolerance": tolerance, "candidateToBaseline": ratios}


def leaderboard_row(name: str, report: dict) -> dict:
    interval = report["macroConfidenceIntervals"]["f1"]
    constraints = report.get("constraints") or {}
    return {
        "run": name,
        "queries": report["queries"],
        "macroF1": report["macro"]["f1"],
        "f1Low": interval["low"],
        "f1High": interval["high"],
        "macroPrecision": report["macro"]["precision"],
        "macroRecall": report["macro"]["recall"],
        "MAP": report["macro"]["averagePrecision"],
        "MRR": report["macro"]["reciprocalRank"],
        "nDCG": report["macro"]["ndcg"],
        "constraintF1": constraints.get("f1"),
        "fieldCoverage": report["structure"]["paperFieldCoverage"],
        "evidenceCoverage": report["structure"]["evidenceCoverage"],
        "apiCallsMean": efficiency_mean(report, "apiCalls"),
        "tokensMean": efficiency_mean(report, "llmTokens"),
        "latencyMeanMs": efficiency_mean(report, "latencyMs"),
        "failedQueries": report.get("reliability", {}).get("failedQueries", 0),
        "failureRate": report.get("reliability", {}).get("failureRate", 0.0),
        "missingPredictions": len(report["missingPredictions"]),
    }


def markdown_table(rows: list[dict], primary_k: int) -> str:
    headers = ["Run", f"F1@{primary_k}", "95% CI", "Recall", "Precision", "MAP", "nDCG", "Tokens", "API calls", "Latency ms", "Failures"]
    lines = [
        f"# ESASR experiment comparison (K={primary_k})",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] + ["---:"] * (len(headers) - 1)) + " |",
    ]
    for row in rows:
        cells = [
            row["run"],
            f"{row['macroF1']:.4f}",
            f"[{row['f1Low']:.4f}, {row['f1High']:.4f}]",
            f"{row['macroRecall']:.4f}",
            f"{row['macroPrecision']:.4f}",
            f"{row['MAP']:.4f}",
            f"{row['nDCG']:.4f}",
            "-" if row["tokensMean"] is None else f"{row['tokensMean']:.1f}",
            "-" if row["apiCallsMean"] is None else f"{row['apiCallsMean']:.2f}",
            "-" if row["latencyMeanMs"] is None else f"{row['latencyMeanMs']:.1f}",
            f"{row['failedQueries']}/{row['queries']}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            "F1 is the competition-facing set metric. MAP/nDCG diagnose ranking quality; "
            "Token, API-call, and latency columns must be checked before claiming an ablation gain under equal budget.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare multiple prediction files with paired bootstrap deltas.")
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--run", required=True, action="append", type=parse_run, metavar="NAME=PATH")
    parser.add_argument("--k", type=int, action="append", help="Repeat for multiple cutoffs (default: 5,10,20)")
    parser.add_argument("--primary-k", type=int, default=20)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--budget-tolerance", type=float, default=0.05)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-csv", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()

    cutoffs = sorted(set(args.k or [5, 10, 20]))
    if min(cutoffs) < 1 or args.primary_k < 1:
        parser.error("cutoffs must be positive")
    if args.primary_k not in cutoffs:
        cutoffs.append(args.primary_k)
        cutoffs.sort()
    if args.bootstrap_samples < 1:
        parser.error("--bootstrap-samples must be at least 1")
    if not 0 < args.confidence < 1:
        parser.error("--confidence must be between 0 and 1")
    if args.budget_tolerance < 0:
        parser.error("--budget-tolerance cannot be negative")

    gold_rows = read_jsonl(args.gold)
    run_names = [name for name, _ in args.run]
    if len(run_names) != len(set(run_names)):
        parser.error("run names must be unique")

    runs: dict[str, dict] = {}
    for name, path in args.run:
        predictions = read_jsonl(path)
        runs[name] = {
            "path": str(path),
            "cutoffs": evaluate_cutoffs(
                gold_rows,
                predictions,
                cutoffs,
                bootstrap_samples=args.bootstrap_samples,
                confidence=args.confidence,
                seed=args.seed,
            ),
        }

    baseline_name = run_names[0]
    baseline = runs[baseline_name]["cutoffs"][str(args.primary_k)]
    comparisons: dict[str, dict] = {}
    for name in run_names[1:]:
        candidate = runs[name]["cutoffs"][str(args.primary_k)]
        comparisons[name] = {
            "vs": baseline_name,
            "pairedF1": paired_bootstrap_delta(
                baseline["perQuery"],
                candidate["perQuery"],
                "f1",
                samples=args.bootstrap_samples,
                confidence=args.confidence,
                seed=args.seed,
            ),
            "pairedRecall": paired_bootstrap_delta(
                baseline["perQuery"],
                candidate["perQuery"],
                "recall",
                samples=args.bootstrap_samples,
                confidence=args.confidence,
                seed=args.seed + 1,
            ),
            "observedBudget": budget_comparison(baseline, candidate, args.budget_tolerance),
        }

    rows = [leaderboard_row(name, runs[name]["cutoffs"][str(args.primary_k)]) for name in run_names]
    payload = {
        "protocol": {
            "cutoffs": cutoffs,
            "primaryK": args.primary_k,
            "baseline": baseline_name,
            "bootstrapSamples": args.bootstrap_samples,
            "confidence": args.confidence,
            "seed": args.seed,
            "budgetTolerance": args.budget_tolerance,
        },
        "leaderboard": rows,
        "comparisons": comparisons,
        "runs": runs,
    }

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.out_csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    rendered = markdown_table(rows, args.primary_k)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
