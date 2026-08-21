"""Precision, recall and F1 metrics for paper-set retrieval."""

from __future__ import annotations

import re
from statistics import mean


def _normalize_doi(value: str) -> str:
    cleaned = value.strip().casefold()
    cleaned = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", cleaned)
    return cleaned.removeprefix("doi:").strip()


def _normalize_title(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold())


def paper_keys(value: str | dict) -> set[str]:
    """Build all stable identities available for a paper."""
    keys: set[str] = set()
    if isinstance(value, str):
        cleaned = value.strip()
        lowered = cleaned.casefold()
        if lowered.startswith("doi:") or lowered.startswith("http") and "doi.org/" in lowered:
            doi = _normalize_doi(cleaned)
            if doi:
                keys.add(f"doi:{doi}")
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
        keys.add(f"doi:{_normalize_doi(str(doi))}")
    for field in ("id", "paper_id", "paperId", "sourceId"):
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


def evaluate_query(
    relevant: list[str | dict],
    predicted: list[str | dict],
    k: int = 20,
) -> dict:
    gold_keys = [paper_keys(item) for item in relevant]
    predictions = predicted[:k]
    matched_gold: set[int] = set()
    true_positives = 0

    for prediction in predictions:
        prediction_keys = paper_keys(prediction)
        for index, expected_keys in enumerate(gold_keys):
            if index not in matched_gold and prediction_keys & expected_keys:
                matched_gold.add(index)
                true_positives += 1
                break

    false_positives = len(predictions) - true_positives
    false_negatives = len(gold_keys) - true_positives
    precision = true_positives / len(predictions) if predictions else 0.0
    recall = true_positives / len(gold_keys) if gold_keys else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "relevant": len(gold_keys),
        "returned": len(predictions),
    }


def evaluate_dataset(
    gold_rows: list[dict],
    prediction_rows: list[dict],
    k: int = 20,
) -> dict:
    prediction_by_id = {
        str(row.get("id") or row.get("query_id")): row
        for row in prediction_rows
    }
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
        metrics = evaluate_query(relevant, predicted, k)
        per_query.append(
            {
                "id": query_id,
                "query": gold.get("query", ""),
                **metrics,
            }
        )

    tp = sum(row["tp"] for row in per_query)
    fp = sum(row["fp"] for row in per_query)
    fn = sum(row["fn"] for row in per_query)
    micro_precision = tp / (tp + fp) if tp + fp else 0.0
    micro_recall = tp / (tp + fn) if tp + fn else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision + micro_recall
        else 0.0
    )

    return {
        "k": k,
        "queries": len(per_query),
        "missingPredictions": missing_predictions,
        "macro": {
            "precision": round(mean(row["precision"] for row in per_query), 6) if per_query else 0.0,
            "recall": round(mean(row["recall"] for row in per_query), 6) if per_query else 0.0,
            "f1": round(mean(row["f1"] for row in per_query), 6) if per_query else 0.0,
        },
        "micro": {
            "precision": round(micro_precision, 6),
            "recall": round(micro_recall, 6),
            "f1": round(micro_f1, 6),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        },
        "perQuery": per_query,
    }
