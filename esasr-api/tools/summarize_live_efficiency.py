#!/usr/bin/env python3
"""Summarize measured planner tokens and live retrieval efficiency."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def describe(values: list[float]) -> dict:
    if not values:
        return {"total": 0, "mean": 0, "median": 0, "p95": 0, "min": 0, "max": 0}
    return {
        "total": round(sum(values), 4),
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "p95": round(percentile(values, 0.95), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", required=True, type=Path)
    parser.add_argument("--predictions", default="predictions_D.jsonl")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    root = args.experiment_dir
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    gold = read_jsonl(root / "gold.jsonl")
    plans = read_jsonl(root / "plans.jsonl")
    predictions = read_jsonl(root / args.predictions)
    gold_source = {row["id"]: row.get("source", "unknown") for row in gold}

    if len(plans) != len(gold) or len(predictions) != len(gold):
        raise ValueError(
            f"incomplete run: gold={len(gold)} plans={len(plans)} predictions={len(predictions)}"
        )

    token_fields = ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")
    token_values = {
        field: [int(row["plan"].get("usage", {}).get(field, 0) or 0) for row in plans]
        for field in token_fields
    }
    llm_plans = [row for row in plans if row["plan"].get("plannerMode") == "llm"]
    llm_token_values = {
        field: [int(row["plan"].get("usage", {}).get(field, 0) or 0) for row in llm_plans]
        for field in token_fields
    }

    source_rows: dict[str, list[dict]] = defaultdict(list)
    for row in predictions:
        source_rows[gold_source[row["id"]]].append(row)

    source_breakdown = {}
    for source, rows in sorted(source_rows.items()):
        source_breakdown[source] = {
            "queries": len(rows),
            "apiCalls": describe([row["metrics"].get("apiCalls", 0) for row in rows]),
            "latencyMs": describe([row["metrics"].get("totalDurationMs", 0) for row in rows]),
            "queriesWithFailures": sum(bool(row["metrics"].get("failures")) for row in rows),
        }

    prompt = sum(token_values["prompt_tokens"])
    completion = sum(token_values["completion_tokens"])
    # DeepSeek prices output reasoning tokens as part of completion tokens; do not add them twice.
    estimated_cost = {
        "currency": "USD",
        "basis": "all prompt tokens charged as cache-miss input; completion_tokens already include reasoning",
        "offPeak": round(prompt * 0.22 / 1_000_000 + completion * 0.66 / 1_000_000, 6),
        "peak": round(prompt * 0.44 / 1_000_000 + completion * 1.32 / 1_000_000, 6),
        "pricingSnapshot": "DeepSeek API documentation, accessed 2026-08-28",
    }

    failures = [row for row in predictions if row["metrics"].get("failures")]
    summary = {
        "protocol": {
            "queries": len(gold),
            "sampling": manifest["dataset"].get("selection"),
            "perSource": manifest["dataset"].get("perSource"),
            "seed": manifest["dataset"].get("seed"),
            "provider": manifest.get("provider"),
            "requestedModel": manifest.get("model"),
            "responseModels": dict(Counter(row["plan"].get("responseModel") for row in llm_plans)),
            "plannerCachePolicy": manifest.get("plannerCachePolicy"),
            "retrievalConfiguration": "D: OpenAlex + Semantic Scholar with coverage-gap-driven second round",
            "maximumLogicalRetrievalCallsPerQuery": 8,
            "tokenSource": "DeepSeek API response usage; no tokenizer estimate",
        },
        "planning": {
            "plannerModes": dict(Counter(row["plan"].get("plannerMode") for row in plans)),
            "requestAttempts": sum(row["plan"].get("planningAttempts", 1) for row in plans),
            "failedAttempts": sum(row["plan"].get("planningFailedAttempts", 0) for row in plans),
            "allQueries": {field: describe(values) for field, values in token_values.items()},
            "llmQueriesOnly": {field: describe(values) for field, values in llm_token_values.items()},
        },
        "retrieval": {
            "logicalApiCalls": describe([row["metrics"].get("apiCalls", 0) for row in predictions]),
            "endToEndLatencyMs": describe(
                [row["metrics"].get("totalDurationMs", 0) for row in predictions]
            ),
            "returnedPapers": describe([len(row.get("predicted", [])) for row in predictions]),
            "completedQueries": len(predictions),
            "queriesWithExternalFailures": len(failures),
            "externalFailureEvents": sum(len(row["metrics"].get("failures", [])) for row in failures),
            "failureTypes": dict(
                Counter(item for row in failures for item in row["metrics"].get("failures", []))
            ),
            "sourceBreakdown": source_breakdown,
        },
        "estimatedCost": estimated_cost,
        "limitations": [
            "This online sample measures operational cost and latency, not the frozen-corpus quality headline.",
            "Live API latency and failure rates depend on provider load and rate limits.",
            "The cost is an estimate from the pricing snapshot because cached-input token detail was not logged.",
        ],
    }

    output = args.out or root / "online_efficiency_summary.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
