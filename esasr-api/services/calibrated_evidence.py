"""Frozen, auditable calibration for MEFR ranking and EGRR routing.

Coefficients were fitted on the historical 200-query development set.  The
held-out 200-query validation protocol and model artifact are stored under
``experiments/core_module_ablations/calibrated_validation``.
"""

from __future__ import annotations

import math
from statistics import mean


BASE_MEAN = (0.0264261304, 0.1384625042, 0.2897687277)
BASE_SCALE = (0.0874545320, 0.1420910809, 0.1907802399)
BASE_COEFFICIENT = (0.7051503532, 0.1183906369, 0.8050068856)
BASE_INTERCEPT = -0.9289564779

EGRR_MEAN = (0.3395833333, 0.6404557730, 0.4404693432, 0.99525)
EGRR_SCALE = (0.1282731190, 0.1598914085, 0.1465443082, 0.0670069959)
EGRR_COEFFICIENT = (-0.0028797417, -0.0032729281, 0.0050128650, 0.0013437144)
EGRR_INTERCEPT = 0.0007713070
EGRR_TRIGGER_THRESHOLD = 0.0085738617


def _linear(features, means, scales, coefficients, intercept):
    return intercept + sum(
        coefficient * ((float(value) - center) / scale)
        for value, center, scale, coefficient in zip(features, means, scales, coefficients)
    )


def calibrated_base_score(
    original_reciprocal_rank: float,
    title_coverage: float,
    abstract_coverage: float,
) -> float:
    """Score the inexpensive candidate prefix without unreplicated RRF uplift."""
    logit = _linear(
        (original_reciprocal_rank, title_coverage, abstract_coverage),
        BASE_MEAN,
        BASE_SCALE,
        BASE_COEFFICIENT,
        BASE_INTERCEPT,
    )
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))


def egrr_marginal_gain(
    normalized_query_length: float,
    best_top10_coverage: float,
    mean_top10_coverage: float,
    top20_uniqueness: float,
) -> float:
    """Predict the marginal quality value of a second retrieval round."""
    return _linear(
        (
            normalized_query_length,
            best_top10_coverage,
            mean_top10_coverage,
            top20_uniqueness,
        ),
        EGRR_MEAN,
        EGRR_SCALE,
        EGRR_COEFFICIENT,
        EGRR_INTERCEPT,
    )


def egrr_decision(query_terms: set[str], paper_term_sets: list[set[str]]) -> dict:
    """Return an auditable route/stop decision from first-round evidence only."""
    coverages = [
        len(query_terms & terms) / max(1, len(query_terms))
        for terms in paper_term_sets[:10]
    ]
    top20 = paper_term_sets[:20]
    features = {
        "normalizedQueryLength": min(1.0, len(query_terms) / 24),
        "bestTop10Coverage": max(coverages, default=0.0),
        "meanTop10Coverage": mean(coverages) if coverages else 0.0,
        "top20Uniqueness": 1.0 if top20 else 0.0,
    }
    gain = egrr_marginal_gain(*features.values())
    return {
        "route": gain > EGRR_TRIGGER_THRESHOLD,
        "predictedMarginalGain": round(gain, 6),
        "threshold": EGRR_TRIGGER_THRESHOLD,
        "features": features,
    }
