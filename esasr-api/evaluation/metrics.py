"""Reproducible retrieval, ranking, structure, constraint, and cost metrics."""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from statistics import mean, median
from typing import Iterable


def _round(value: float) -> float:
    return round(value, 6)


def _normalize_doi(value: str) -> str:
    cleaned = value.strip().casefold()
    cleaned = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", cleaned)
    return cleaned.removeprefix("doi:").strip()


def _normalize_title(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold())


def _normalize_arxiv(value: str) -> str:
    cleaned = value.strip().casefold()
    cleaned = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", cleaned)
    cleaned = cleaned.removeprefix("arxiv:").removeprefix("arxiv.")
    return cleaned.removesuffix(".pdf").split("v", 1)[0].strip()


def paper_keys(value: str | dict) -> set[str]:
    """Build all stable identities available for a paper."""
    keys: set[str] = set()
    if isinstance(value, str):
        cleaned = value.strip()
        lowered = cleaned.casefold()
        if lowered.startswith("arxiv:") or "arxiv.org/abs/" in lowered:
            arxiv_id = _normalize_arxiv(cleaned)
            if arxiv_id:
                keys.add(f"arxiv:{arxiv_id}")
        elif lowered.startswith("doi:") or lowered.startswith("http") and "doi.org/" in lowered:
            doi = _normalize_doi(cleaned)
            if doi:
                keys.add(f"doi:{doi}")
                if doi.startswith("10.48550/arxiv."):
                    keys.add(f"arxiv:{_normalize_arxiv(doi.removeprefix('10.48550/'))}")
        elif lowered.startswith("id:"):
            keys.add(f"id:{cleaned[3:].strip().casefold()}")
        elif lowered.startswith("title:"):
            title = _normalize_title(cleaned[6:])
            if title:
                keys.add(f"title:{title}")
        elif re.match(r"^10\.\d{4,9}/", lowered):
            keys.add(f"doi:{_normalize_doi(cleaned)}")
        else:
            keys.add(f"id:{lowered}")
            title = _normalize_title(cleaned)
            if title:
                keys.add(f"title:{title}")
        return keys

    doi = value.get("doi")
    if doi:
        normalized_doi = _normalize_doi(str(doi))
        keys.add(f"doi:{normalized_doi}")
        if normalized_doi.startswith("10.48550/arxiv."):
            keys.add(f"arxiv:{_normalize_arxiv(normalized_doi.removeprefix('10.48550/'))}")
    for field in ("arxivId", "arxiv_id", "arxiv"):
        arxiv_id = value.get(field)
        if arxiv_id:
            keys.add(f"arxiv:{_normalize_arxiv(str(arxiv_id))}")
    for field in ("id", "paper_id", "paperId", "sourceId", "openalex_id", "s2_id"):
        identifier = value.get(field)
        if identifier:
            keys.add(f"id:{str(identifier).casefold()}")
    title = value.get("title")
    if title:
        normalized = _normalize_title(str(title))
        if normalized:
            keys.add(f"title:{normalized}")
    canonical = value.get("canonicalKey")
    if canonical:
        keys.update(paper_keys(str(canonical)))
    return keys


def _relevance_grade(value: str | dict) -> float:
    if not isinstance(value, dict):
        return 1.0
    for field in ("relevance", "grade", "label"):
        raw = value.get(field)
        if isinstance(raw, (int, float)):
            return max(0.0, float(raw))
    return 1.0


def _match_ranked(
    relevant: list[str | dict],
    predicted: list[str | dict],
    k: int,
) -> tuple[list[float], int, int]:
    gold = [(paper_keys(item), _relevance_grade(item)) for item in relevant]
    gold = [(keys, grade) for keys, grade in gold if keys and grade > 0]
    matched_gold: set[int] = set()
    grades: list[float] = []
    duplicates = 0

    for prediction in predicted[:k]:
        prediction_keys = paper_keys(prediction)
        matched_index: int | None = None
        for index, (expected_keys, _) in enumerate(gold):
            if prediction_keys & expected_keys:
                matched_index = index
                break
        if matched_index is None:
            grades.append(0.0)
        elif matched_index in matched_gold:
            grades.append(0.0)
            duplicates += 1
        else:
            matched_gold.add(matched_index)
            grades.append(gold[matched_index][1])
    return grades, len(gold), duplicates


def _average_precision(binary_relevance: list[int], relevant_count: int) -> float:
    if not relevant_count:
        return 0.0
    hits = 0
    total = 0.0
    for rank, is_relevant in enumerate(binary_relevance, start=1):
        if is_relevant:
            hits += 1
            total += hits / rank
    return total / relevant_count


def _dcg(grades: list[float]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def evaluate_query(
    relevant: list[str | dict],
    predicted: list[str | dict],
    k: int = 20,
) -> dict:
    """Evaluate one ranked result list at K with set and rank metrics."""
    if k < 1:
        raise ValueError("k must be at least 1")
    predictions = predicted[:k]
    grades, relevant_count, duplicates = _match_ranked(relevant, predictions, k)
    binary = [int(grade > 0) for grade in grades]
    true_positives = sum(binary)
    false_positives = len(predictions) - true_positives
    false_negatives = relevant_count - true_positives
    precision = true_positives / len(predictions) if predictions else 0.0
    recall = true_positives / relevant_count if relevant_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    first_rank = next((index for index, hit in enumerate(binary, start=1) if hit), None)
    reciprocal_rank = 1 / first_rank if first_rank else 0.0
    average_precision = _average_precision(binary, relevant_count)
    ideal_grades = sorted(
        (
            _relevance_grade(item)
            for item in relevant
            if paper_keys(item) and _relevance_grade(item) > 0
        ),
        reverse=True,
    )[:k]
    ideal_dcg = _dcg(ideal_grades)
    ndcg = _dcg(grades) / ideal_dcg if ideal_dcg else 0.0

    return {
        "precision": _round(precision),
        "recall": _round(recall),
        "f1": _round(f1),
        "averagePrecision": _round(average_precision),
        "reciprocalRank": _round(reciprocal_rank),
        "ndcg": _round(ndcg),
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "relevant": relevant_count,
        "returned": len(predictions),
        "duplicatePredictions": duplicates,
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _bootstrap_interval(values: list[float], samples: int, confidence: float, seed: int) -> dict:
    if not values or samples <= 0:
        return {"low": 0.0, "high": 0.0, "confidence": confidence, "samples": samples}
    rng = random.Random(seed)
    estimates = [mean(rng.choices(values, k=len(values))) for _ in range(samples)]
    alpha = (1 - confidence) / 2
    return {
        "low": _round(_percentile(estimates, alpha)),
        "high": _round(_percentile(estimates, 1 - alpha)),
        "confidence": confidence,
        "samples": samples,
    }


def _flatten_constraints(value: object, prefix: str = "") -> set[str]:
    flattened: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_constraints(item, child))
    elif isinstance(value, list):
        for item in value:
            flattened.update(_flatten_constraints(item, prefix))
    elif value is not None and value != "":
        normalized = re.sub(r"\s+", " ", str(value).strip().casefold())
        flattened.add(f"{prefix}:{normalized}")
    return flattened


def evaluate_constraints(gold: dict, prediction: dict) -> dict | None:
    expected = gold.get("constraints")
    actual = prediction.get("constraints")
    if actual is None and isinstance(prediction.get("plan"), dict):
        actual = prediction["plan"].get("constraints")
    if not isinstance(expected, dict):
        return None
    expected_slots = _flatten_constraints(expected)
    actual_slots = _flatten_constraints(actual or {})
    tp = len(expected_slots & actual_slots)
    fp = len(actual_slots - expected_slots)
    fn = len(expected_slots - actual_slots)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": _round(precision),
        "recall": _round(recall),
        "f1": _round(f1),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _first_number(row: dict, *paths: tuple[str, ...]) -> float | None:
    for path in paths:
        current: object = row
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        number = _number(current)
        if number is not None:
            return number
    return None


def extract_costs(prediction: dict) -> dict:
    """Extract optional pipeline measurements without requiring one export schema."""
    fields = {
        "apiCalls": (("metrics", "apiCalls"), ("metrics", "api_calls"), ("apiCalls",)),
        "httpAttempts": (("metrics", "httpAttempts"), ("httpAttempts",)),
        "llmTokens": (("metrics", "llmTokens"), ("metrics", "totalTokens"), ("llmTokens",)),
        "promptTokens": (("metrics", "llmPromptTokens"), ("metrics", "promptTokens")),
        "completionTokens": (("metrics", "llmCompletionTokens"), ("metrics", "completionTokens")),
        "reasoningTokens": (("metrics", "llmReasoningTokens"), ("metrics", "reasoningTokens")),
        "latencyMs": (
            ("metrics", "totalDurationMs"),
            ("metrics", "latencyMs"),
            ("totalDurationMs",),
            ("latencyMs",),
        ),
    }
    return {name: value for name, paths in fields.items() if (value := _first_number(prediction, *paths)) is not None}


def evaluate_structure(prediction: dict, k: int) -> dict:
    papers = prediction.get("predicted") or prediction.get("papers") or []
    papers = papers[:k] if isinstance(papers, list) else []
    required_fields = ("title", "authors", "year", "venue", "source")
    field_slots = len(papers) * len(required_fields)
    present_fields = sum(
        1
        for paper in papers
        if isinstance(paper, dict)
        for field in required_fields
        if paper.get(field) not in (None, "", [])
    )
    evidence_fields = ("matchReasons", "matchedTerms", "recommendationReason", "reason", "evidence")
    evidence_count = sum(
        1
        for paper in papers
        if isinstance(paper, dict) and any(paper.get(field) not in (None, "", []) for field in evidence_fields)
    )
    trace = prediction.get("trace") or prediction.get("steps") or prediction.get("searchSteps")
    graph = prediction.get("graph") or {}
    graph_available = isinstance(graph, dict) and bool(graph.get("nodes"))
    return {
        "paperFieldCoverage": _round(present_fields / field_slots) if field_slots else 0.0,
        "evidenceCoverage": _round(evidence_count / len(papers)) if papers else 0.0,
        "traceAvailable": bool(trace),
        "graphAvailable": graph_available,
    }


def _aggregate_costs(per_query: list[dict], tp: int) -> dict:
    names = ("apiCalls", "httpAttempts", "llmTokens", "promptTokens", "completionTokens", "reasoningTokens", "latencyMs")
    result: dict[str, dict] = {}
    for name in names:
        values = [row["costs"][name] for row in per_query if name in row["costs"]]
        if values:
            result[name] = {
                "count": len(values),
                "total": _round(sum(values)),
                "mean": _round(mean(values)),
                "median": _round(median(values)),
                "p95": _round(_percentile(values, 0.95)),
            }
    for name in ("apiCalls", "httpAttempts", "llmTokens", "latencyMs"):
        if name in result:
            result[name]["perTruePositive"] = _round(result[name]["total"] / tp) if tp else None
    return result


def _aggregate_optional(per_query: list[dict], key: str, metric_names: Iterable[str]) -> dict | None:
    rows = [row[key] for row in per_query if row.get(key) is not None]
    if not rows:
        return None
    return {name: _round(mean(row[name] for row in rows)) for name in metric_names}


def _summarize_query_rows(rows: list[dict]) -> dict:
    """Summarize a query slice without rerunning matching."""
    tp = sum(row["tp"] for row in rows)
    fp = sum(row["fp"] for row in rows)
    fn = sum(row["fn"] for row in rows)
    micro_precision = tp / (tp + fp) if tp + fp else 0.0
    micro_recall = tp / (tp + fn) if tp + fn else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision + micro_recall
        else 0.0
    )
    macro_names = ("precision", "recall", "f1", "averagePrecision", "reciprocalRank", "ndcg")
    return {
        "queries": len(rows),
        "macro": {name: _round(mean(row[name] for row in rows)) for name in macro_names},
        "micro": {
            "precision": _round(micro_precision),
            "recall": _round(micro_recall),
            "f1": _round(micro_f1),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        },
    }


def _grouped_summaries(per_query: list[dict]) -> dict:
    grouped: dict[str, dict[str, dict]] = {}
    fields = ("split", "domain", "language", "constraint_type", "difficulty")
    for field in fields:
        values = sorted({str(row["groups"][field]) for row in per_query if field in row["groups"]})
        if values:
            grouped[field] = {
                value: _summarize_query_rows(
                    [row for row in per_query if str(row["groups"].get(field)) == value]
                )
                for value in values
            }
    return grouped


def evaluate_dataset(
    gold_rows: list[dict],
    prediction_rows: list[dict],
    k: int = 20,
    *,
    bootstrap_samples: int = 1000,
    confidence: float = 0.95,
    seed: int = 2026,
) -> dict:
    prediction_ids = [str(row.get("id") or row.get("query_id")) for row in prediction_rows]
    prediction_by_id = {
        query_id: row for query_id, row in zip(prediction_ids, prediction_rows) if query_id != "None"
    }
    duplicate_prediction_ids = sorted(
        {query_id for query_id in prediction_ids if query_id != "None" and prediction_ids.count(query_id) > 1}
    )
    gold_ids = {
        str(row.get("id") or row.get("query_id") or index) for index, row in enumerate(gold_rows)
    }
    extra_prediction_ids = sorted(set(prediction_by_id) - gold_ids)
    per_query: list[dict] = []
    missing_predictions: list[str] = []

    for index, gold in enumerate(gold_rows):
        query_id = str(gold.get("id") or gold.get("query_id") or index)
        prediction = prediction_by_id.get(query_id)
        if prediction is None:
            missing_predictions.append(query_id)
            prediction = {}
        relevant = gold.get("relevant") or gold.get("relevant_papers") or []
        predicted = prediction.get("predicted") or prediction.get("papers") or []
        failures = prediction.get("failures")
        if failures is None and isinstance(prediction.get("metrics"), dict):
            failures = prediction["metrics"].get("failures")
        failures = [str(item) for item in failures or []]
        metrics = evaluate_query(relevant, predicted, k)
        per_query.append(
            {
                "id": query_id,
                "query": gold.get("query", ""),
                "groups": {
                    key: gold[key]
                    for key in ("split", "domain", "language", "constraint_type", "difficulty")
                    if key in gold
                },
                **metrics,
                "constraints": evaluate_constraints(gold, prediction),
                "structure": evaluate_structure(prediction, k),
                "costs": extract_costs(prediction),
                "failures": failures,
            }
        )

    tp = sum(row["tp"] for row in per_query)
    fp = sum(row["fp"] for row in per_query)
    fn = sum(row["fn"] for row in per_query)
    micro_precision = tp / (tp + fp) if tp + fp else 0.0
    micro_recall = tp / (tp + fn) if tp + fn else 0.0
    micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall) if micro_precision + micro_recall else 0.0
    macro_names = ("precision", "recall", "f1", "averagePrecision", "reciprocalRank", "ndcg")
    macro = {name: _round(mean(row[name] for row in per_query)) if per_query else 0.0 for name in macro_names}
    intervals = {
        name: _bootstrap_interval([row[name] for row in per_query], bootstrap_samples, confidence, seed + offset)
        for offset, name in enumerate(macro_names)
    }
    constraints = _aggregate_optional(per_query, "constraints", ("precision", "recall", "f1"))
    structure = {
        "paperFieldCoverage": _round(mean(row["structure"]["paperFieldCoverage"] for row in per_query)) if per_query else 0.0,
        "evidenceCoverage": _round(mean(row["structure"]["evidenceCoverage"] for row in per_query)) if per_query else 0.0,
        "traceAvailableRate": _round(mean(float(row["structure"]["traceAvailable"]) for row in per_query)) if per_query else 0.0,
        "graphAvailableRate": _round(mean(float(row["structure"]["graphAvailable"]) for row in per_query)) if per_query else 0.0,
    }
    failure_counter = Counter(
        failure
        for row in per_query
        for failure in row["failures"]
    )
    failed_queries = sum(bool(row["failures"]) for row in per_query)

    return {
        "k": k,
        "queries": len(per_query),
        "missingPredictions": missing_predictions,
        "duplicatePredictionIds": duplicate_prediction_ids,
        "extraPredictionIds": extra_prediction_ids,
        "macro": macro,
        "macroConfidenceIntervals": intervals,
        "micro": {
            "precision": _round(micro_precision),
            "recall": _round(micro_recall),
            "f1": _round(micro_f1),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        },
        "constraints": constraints,
        "structure": structure,
        "efficiency": _aggregate_costs(per_query, tp),
        "reliability": {
            "completeQueries": len(per_query) - failed_queries,
            "failedQueries": failed_queries,
            "failureRate": _round(failed_queries / len(per_query)) if per_query else 0.0,
            "failureEvents": sum(failure_counter.values()),
            "failureTypes": dict(sorted(failure_counter.items())),
        },
        "groups": _grouped_summaries(per_query),
        "perQuery": per_query,
    }


def evaluate_cutoffs(
    gold_rows: list[dict],
    prediction_rows: list[dict],
    cutoffs: Iterable[int],
    *,
    bootstrap_samples: int = 1000,
    confidence: float = 0.95,
    seed: int = 2026,
) -> dict[str, dict]:
    unique = sorted(set(cutoffs))
    if not unique or unique[0] < 1:
        raise ValueError("cutoffs must contain positive integers")
    return {
        str(k): evaluate_dataset(
            gold_rows,
            prediction_rows,
            k,
            bootstrap_samples=bootstrap_samples,
            confidence=confidence,
            seed=seed,
        )
        for k in unique
    }


def paired_bootstrap_delta(
    baseline_per_query: list[dict],
    candidate_per_query: list[dict],
    metric: str = "f1",
    *,
    samples: int = 5000,
    confidence: float = 0.95,
    seed: int = 2026,
) -> dict:
    baseline = {row["id"]: row for row in baseline_per_query}
    candidate = {row["id"]: row for row in candidate_per_query}
    ids = sorted(set(baseline) & set(candidate))
    deltas = [candidate[query_id][metric] - baseline[query_id][metric] for query_id in ids]
    if not deltas:
        return {"metric": metric, "queries": 0, "delta": 0.0, "low": 0.0, "high": 0.0, "winRate": 0.0}
    interval = _bootstrap_interval(deltas, samples, confidence, seed)
    return {
        "metric": metric,
        "queries": len(deltas),
        "delta": _round(mean(deltas)),
        "low": interval["low"],
        "high": interval["high"],
        "confidence": confidence,
        "samples": samples,
        "winRate": _round(sum(delta > 0 for delta in deltas) / len(deltas)),
    }
