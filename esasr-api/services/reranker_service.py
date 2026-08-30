"""Optional local Cross Encoder reranking with lazy model loading."""

from __future__ import annotations

import math
import threading
from typing import Protocol

from config import cfg


BREADTH_POLICIES: dict[int, dict[str, float | str]] = {
    1: {"label": "精准", "target_mass": 0.35, "min_score": 0.60, "min_ratio": 0.85, "max_gap": 0.08},
    2: {"label": "聚焦", "target_mass": 0.50, "min_score": 0.55, "min_ratio": 0.70, "max_gap": 0.10},
    3: {"label": "均衡", "target_mass": 0.65, "min_score": 0.45, "min_ratio": 0.50, "max_gap": 0.12},
    4: {"label": "扩展", "target_mass": 0.80, "min_score": 0.20, "min_ratio": 0.20, "max_gap": 0.14},
    5: {"label": "广泛", "target_mass": 1.00, "min_score": 0.20, "min_ratio": 0.15, "max_gap": 1.00},
}


class PaperReranker(Protocol):
    model_name: str

    def rerank(self, query: str, papers: list[dict], top_n: int) -> list[dict]:
        ...


def confidence_aware_select(
    papers: list[dict],
    *,
    max_k: int = 2,
    min_score: float = 0.60,
    min_ratio: float = 0.85,
    max_drop: float = 0.10,
) -> list[dict]:
    """Select a calibrated contiguous prefix while always retaining Top-1.

    The rule uses only post-reranking scores. It therefore adds no model call
    and cannot skip ahead to a lower-ranked candidate after rejecting a rank.
    """
    if not papers:
        return []
    selected = [papers[0]]
    top_score = max(float(papers[0].get("relevanceScore") or 0.0), 1e-12)
    previous_score = top_score
    for paper in papers[1 : max(1, max_k)]:
        score = float(paper.get("relevanceScore") or 0.0)
        if (
            score < min_score
            or score / top_score < min_ratio
            or previous_score - score > max_drop + 1e-12
        ):
            break
        selected.append(paper)
        previous_score = score
    return selected


def confidence_mass_select(
    papers: list[dict],
    *,
    breadth_level: int = 3,
) -> tuple[list[dict], dict]:
    """Select a query-dependent prefix from score mass and boundary gaps.

    No breadth level maps to a fixed K.  Each level changes the target share
    of normalized score mass, the relevance floor, and the score-cliff
    tolerance.  A near-tied candidate is kept even when the target mass has
    already been reached, so the precise level can legitimately return more
    than one paper.  The broad level returns every eligible paper in the
    current candidate pool rather than imposing an arbitrary Top-K.
    """
    if not papers:
        return [], {
            "status": "completed",
            "breadthLevel": max(1, min(int(breadth_level), 5)),
            "selected": 0,
            "eligible": 0,
            "stopReason": "empty_candidate_pool",
        }

    level = max(1, min(int(breadth_level), 5))
    policy = BREADTH_POLICIES[level]
    top_score = max(float(papers[0].get("relevanceScore") or 0.0), 1e-12)
    min_score = float(policy["min_score"])
    min_ratio = float(policy["min_ratio"])
    eligible: list[dict] = []
    eligible_scores: list[float] = []
    for index, paper in enumerate(papers):
        score = max(float(paper.get("relevanceScore") or 0.0), 0.0)
        if index and (score < min_score or score / top_score < min_ratio):
            break
        eligible.append(paper)
        eligible_scores.append(score)

    if not eligible:
        eligible = papers[:1]
        eligible_scores = [max(float(papers[0].get("relevanceScore") or 0.0), 0.0)]

    total_mass = sum(eligible_scores)
    if total_mass <= 1e-12:
        normalized = [1.0] + [0.0] * (len(eligible_scores) - 1)
    else:
        normalized = [score / total_mass for score in eligible_scores]

    target_mass = float(policy["target_mass"])
    if level == 5:
        cutoff = len(eligible)
        stop_reason = "relevance_boundary" if len(eligible) < len(papers) else "candidate_pool_exhausted"
    else:
        cumulative = 0.0
        cutoff = 1
        for index, mass in enumerate(normalized, start=1):
            cumulative += mass
            cutoff = index
            if cumulative + 1e-12 >= target_mass:
                break

        max_gap = float(policy["max_gap"])
        while cutoff < len(eligible):
            previous_score = eligible_scores[cutoff - 1]
            next_score = eligible_scores[cutoff]
            if previous_score - next_score > max_gap + 1e-12:
                break
            cutoff += 1
        if cutoff == len(eligible):
            stop_reason = "relevance_boundary" if len(eligible) < len(papers) else "candidate_pool_exhausted"
        else:
            stop_reason = "significant_score_cliff"

    selected = eligible[:cutoff]
    achieved_mass = sum(normalized[:cutoff])
    return selected, {
        "status": "completed",
        "breadthLevel": level,
        "breadthLabel": str(policy["label"]),
        "targetMass": target_mass,
        "achievedMass": round(achieved_mass, 4),
        "minScore": min_score,
        "minRatio": min_ratio,
        "maxGap": float(policy["max_gap"]),
        "candidatePool": len(papers),
        "eligible": len(eligible),
        "selected": len(selected),
        "stopReason": stop_reason,
    }


def _probability(score: float) -> float:
    if 0.0 <= score <= 1.0:
        return score
    if score >= 40:
        return 1.0
    if score <= -40:
        return 0.0
    return 1.0 / (1.0 + math.exp(-score))


class CrossEncoderReranker:
    """Load a sentence-transformers CrossEncoder only when first used."""

    def __init__(
        self,
        model_name: str,
        batch_size: int = 8,
        max_length: int = 512,
        device: str = "auto",
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length
        self.device = None if device == "auto" else device
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "Cross Encoder dependencies are not installed. "
                    "Install esasr-api/requirements-reranker.txt."
                ) from exc
            self._model = CrossEncoder(
                self.model_name,
                max_length=self.max_length,
                device=self.device,
            )
            return self._model

    def rerank(self, query: str, papers: list[dict], top_n: int) -> list[dict]:
        if not papers:
            return []
        selected = papers[: max(1, min(top_n, len(papers)))]
        pairs = [
            (
                query,
                f"{paper.get('title', '')}\n{paper.get('abstract', '')}"[:6000],
            )
            for paper in selected
        ]
        scores = self._load().predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        reranked: list[dict] = []
        for paper, raw_score in zip(selected, scores):
            if hasattr(raw_score, "item"):
                raw_score = raw_score.item()
            if isinstance(raw_score, (list, tuple)):
                raw_score = raw_score[-1]
            cross_score = _probability(float(raw_score))
            base_score = float(paper.get("relevanceScore") or 0)
            final_score = 0.65 * cross_score + 0.35 * base_score
            reranked.append(
                {
                    **paper,
                    "baseRelevanceScore": round(base_score, 4),
                    "crossEncoderScore": round(cross_score, 4),
                    "relevanceScore": round(final_score, 4),
                    "relevanceLevel": "高度相关" if final_score >= 0.62 else "部分相关",
                }
            )

        reranked.sort(key=lambda paper: paper["relevanceScore"], reverse=True)
        return reranked


def get_configured_reranker() -> tuple[PaperReranker | None, dict]:
    cross = cfg.ranking.get("cross_encoder")
    breadth = cross.get("breadth_selector") if cross else None
    breadth_metadata = {
        "enabled": bool(breadth.get("enabled", True)) if breadth else True,
        "defaultLevel": int(breadth.get("default_level", 3)) if breadth else 3,
    }
    if not cross or not cross.get("enabled", False):
        return None, {
            "status": "disabled",
            "model": cross.get("model", "") if cross else "",
            "detail": "Cross Encoder 未启用，保留融合排序结果。",
            "breadthSelector": breadth_metadata,
        }

    reranker = CrossEncoderReranker(
        model_name=cross.get("model", "BAAI/bge-reranker-base"),
        batch_size=int(cross.get("batch_size", 8)),
        max_length=int(cross.get("max_length", 512)),
        device=cross.get("device", "auto"),
    )
    adaptive = cross.get("adaptive_selector") or {}
    return reranker, {
        "status": "configured",
        "model": reranker.model_name,
        "topN": int(cross.get("top_n", 40)),
        "threshold": float(cross.get("threshold", 0.0)),
        "adaptiveSelector": {
            "enabled": bool(adaptive.get("enabled", False)),
            "maxK": int(adaptive.get("max_k", 2)),
            "minScore": float(adaptive.get("min_score", 0.60)),
            "minRatio": float(adaptive.get("min_ratio", 0.85)),
            "maxDrop": float(adaptive.get("max_drop", 0.10)),
        },
        "breadthSelector": breadth_metadata,
    }
