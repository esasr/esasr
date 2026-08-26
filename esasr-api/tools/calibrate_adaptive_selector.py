#!/usr/bin/env python3
"""Calibrate and evaluate a confidence-aware variable-size result set.

The selector is intentionally lightweight: it consumes the frozen ranked
candidate list, never looks at test labels during calibration, and adds no
retrieval, LLM, or reranker calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.metrics import evaluate_dataset, paired_bootstrap_delta
from services.reranker_service import confidence_aware_select


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
            raise ValueError(f"{path}:{line_number}: each row must be an object")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def stratified_hash_split(gold_rows: list[dict], dev_fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    """Split within each source using a stable hash; labels never affect membership."""
    grouped: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for index, row in enumerate(gold_rows):
        query_id = str(row.get("id") or row.get("query_id") or index)
        source = str(row.get("source") or "unknown")
        digest = hashlib.sha256(f"{seed}:{query_id}".encode()).hexdigest()
        grouped[source].append((digest, row))

    dev: list[dict] = []
    test: list[dict] = []
    for source in sorted(grouped):
        ranked = [row for _, row in sorted(grouped[source], key=lambda item: item[0])]
        dev_count = round(len(ranked) * dev_fraction)
        if len(ranked) > 1:
            dev_count = min(max(dev_count, 1), len(ranked) - 1)
        dev.extend(ranked[:dev_count])
        test.extend(ranked[dev_count:])
    return dev, test


def prediction_subset(
    gold_rows: list[dict],
    predictions_by_id: dict[str, dict],
    *,
    max_k: int,
    min_score: float = 0.0,
    min_ratio: float = 0.0,
    max_drop: float = 1.0,
) -> list[dict]:
    rows: list[dict] = []
    for index, gold in enumerate(gold_rows):
        query_id = str(gold.get("id") or gold.get("query_id") or index)
        source = predictions_by_id.get(query_id, {})
        candidates = source.get("predicted") or source.get("papers") or []
        selected = confidence_aware_select(
            candidates,
            max_k=max_k,
            min_score=min_score,
            min_ratio=min_ratio,
            max_drop=max_drop,
        )
        output = {key: value for key, value in source.items() if key not in {"predicted", "papers"}}
        output.update({"id": query_id, "query": gold.get("query", ""), "predicted": selected})
        rows.append(output)
    return rows


def compact_metrics(report: dict) -> dict:
    returned = [row["returned"] for row in report["perQuery"]]
    return {
        "queries": report["queries"],
        "macro": report["macro"],
        "f1ConfidenceInterval": report["macroConfidenceIntervals"]["f1"],
        "micro": report["micro"],
        "returnedMean": round(mean(returned), 6) if returned else 0.0,
        "returnedDistribution": dict(sorted(Counter(returned).items())),
    }


def tune_selector(dev_gold: list[dict], predictions_by_id: dict[str, dict]) -> tuple[dict, list[dict]]:
    candidates: list[dict] = []
    for max_k in (2, 3, 4, 5):
        for min_score_int in range(0, 86, 5):
            for min_ratio_int in range(25, 101, 5):
                for max_drop_int in (10, 20, 30, 40, 50, 75, 100):
                    config = {
                        "maxK": max_k,
                        "minScore": min_score_int / 100,
                        "minRatio": min_ratio_int / 100,
                        "maxDrop": max_drop_int / 100,
                    }
                    rows = prediction_subset(
                        dev_gold,
                        predictions_by_id,
                        max_k=max_k,
                        min_score=config["minScore"],
                        min_ratio=config["minRatio"],
                        max_drop=config["maxDrop"],
                    )
                    report = evaluate_dataset(dev_gold, rows, k=max_k, bootstrap_samples=1)
                    returned_mean = mean(row["returned"] for row in report["perQuery"])
                    candidates.append(
                        {
                            **config,
                            "macroF1": report["macro"]["f1"],
                            "macroPrecision": report["macro"]["precision"],
                            "macroRecall": report["macro"]["recall"],
                            "returnedMean": round(returned_mean, 6),
                        }
                    )
    candidates.sort(
        key=lambda row: (
            -row["macroF1"],
            row["returnedMean"],
            row["maxK"],
            -row["minScore"],
            -row["minRatio"],
            row["maxDrop"],
        )
    )
    return candidates[0], candidates[:20]


def markdown_report(payload: dict) -> str:
    protocol = payload["protocol"]
    lines = [
        "# V5 confidence-aware adaptive result-set experiment",
        "",
        "## Protocol",
        "",
        f"- Frozen V3 candidates; no new API, LLM, retrieval, or reranker calls.",
        f"- Stratified deterministic split: dev {protocol['devQueries']}, test {protocol['testQueries']}, seed {protocol['seed']}.",
        "- Thresholds were selected only by dev Macro F1; all final numbers below are held-out test results.",
        f"- Selected rule: maxK={protocol['selectedRule']['maxK']}, minScore={protocol['selectedRule']['minScore']:.2f}, "
        f"minRatio={protocol['selectedRule']['minRatio']:.2f}, maxDrop={protocol['selectedRule']['maxDrop']:.2f}.",
        "",
        "## Held-out test results",
        "",
        "| Method | Precision | Recall | Macro F1 | 95% CI | Avg. returned |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in payload["testResults"].items():
        macro = row["macro"]
        interval = row["f1ConfidenceInterval"]
        lines.append(
            f"| {name} | {macro['precision']:.4f} | {macro['recall']:.4f} | {macro['f1']:.4f} | "
            f"[{interval['low']:.4f}, {interval['high']:.4f}] | {row['returnedMean']:.3f} |"
        )
    delta = payload["comparisons"]["adaptiveVsFixedK1"]
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            f"Adaptive minus fixed Top-1 paired Macro F1 delta: {delta['delta']:.4f}, "
            f"95% CI [{delta['low']:.4f}, {delta['high']:.4f}].",
            "The result is an offline selection ablation on a frozen candidate pool, not an official ScholarGym score. "
            "It does not by itself validate online evidence-gap expansion.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--dev-fraction", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    args = parser.parse_args()
    if not 0 < args.dev_fraction < 1:
        parser.error("--dev-fraction must be between 0 and 1")
    if args.bootstrap_samples < 1:
        parser.error("--bootstrap-samples must be at least 1")

    gold = read_jsonl(args.gold)
    predictions = read_jsonl(args.predictions)
    predictions_by_id = {
        str(row.get("id") or row.get("query_id")): row
        for row in predictions
        if row.get("id") or row.get("query_id")
    }
    dev_gold, test_gold = stratified_hash_split(gold, args.dev_fraction, args.seed)
    selected_rule, tuning_leaderboard = tune_selector(dev_gold, predictions_by_id)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "dev_gold.jsonl", dev_gold)
    write_jsonl(args.out_dir / "test_gold.jsonl", test_gold)

    reports: dict[str, dict] = {}
    full_reports: dict[str, dict] = {}
    output_rows: dict[str, list[dict]] = {}
    for fixed_k in (1, 2, 3, 5):
        name = f"Fixed Top-{fixed_k}"
        rows = prediction_subset(test_gold, predictions_by_id, max_k=fixed_k)
        report = evaluate_dataset(
            test_gold, rows, k=fixed_k, bootstrap_samples=args.bootstrap_samples, seed=args.seed
        )
        output_rows[name] = rows
        full_reports[name] = report
        reports[name] = compact_metrics(report)
        write_jsonl(args.out_dir / f"fixed_k{fixed_k}.jsonl", rows)

    adaptive_rows = prediction_subset(
        test_gold,
        predictions_by_id,
        max_k=selected_rule["maxK"],
        min_score=selected_rule["minScore"],
        min_ratio=selected_rule["minRatio"],
        max_drop=selected_rule["maxDrop"],
    )
    adaptive_report = evaluate_dataset(
        test_gold,
        adaptive_rows,
        k=selected_rule["maxK"],
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    write_jsonl(args.out_dir / "adaptive_predictions.jsonl", adaptive_rows)
    output_rows["Adaptive"] = adaptive_rows
    full_reports["Adaptive"] = adaptive_report
    reports["Adaptive"] = compact_metrics(adaptive_report)

    payload = {
        "protocol": {
            "scope": "frozen V3 candidate-pool selection ablation; not an official leaderboard score",
            "seed": args.seed,
            "devFraction": args.dev_fraction,
            "devQueries": len(dev_gold),
            "testQueries": len(test_gold),
            "selectedRule": {
                key: selected_rule[key] for key in ("maxK", "minScore", "minRatio", "maxDrop")
            },
            "devSelectedMacroF1": selected_rule["macroF1"],
            "tuningCandidates": 4 * 18 * 16 * 7,
            "sourceCounts": {
                "dev": dict(sorted(Counter(str(row.get("source") or "unknown") for row in dev_gold).items())),
                "test": dict(sorted(Counter(str(row.get("source") or "unknown") for row in test_gold).items())),
            },
        },
        "devTuningTop20": tuning_leaderboard,
        "testResults": reports,
        "comparisons": {
            "adaptiveVsFixedK1": paired_bootstrap_delta(
                full_reports["Fixed Top-1"]["perQuery"],
                adaptive_report["perQuery"],
                "f1",
                samples=args.bootstrap_samples,
                seed=args.seed,
            )
        },
    }
    (args.out_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out_dir / "REPORT.md").write_text(markdown_report(payload), encoding="utf-8")
    print(markdown_report(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
