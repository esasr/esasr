"""Optional local Cross Encoder reranking with lazy model loading."""

from __future__ import annotations

import math
import threading
from typing import Protocol

from config import cfg


class PaperReranker(Protocol):
    model_name: str

    def rerank(self, query: str, papers: list[dict], top_n: int) -> list[dict]:
        ...


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
                    "Install scholarseeker-api/requirements-reranker.txt."
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
    if not cross or not cross.get("enabled", False):
        return None, {
            "status": "disabled",
            "model": cross.get("model", "") if cross else "",
            "detail": "Cross Encoder 未启用，保留融合排序结果。",
        }

    reranker = CrossEncoderReranker(
        model_name=cross.get("model", "BAAI/bge-reranker-base"),
        batch_size=int(cross.get("batch_size", 8)),
        max_length=int(cross.get("max_length", 512)),
        device=cross.get("device", "auto"),
    )
    return reranker, {
        "status": "configured",
        "model": reranker.model_name,
        "topN": int(cross.get("top_n", 40)),
    }
