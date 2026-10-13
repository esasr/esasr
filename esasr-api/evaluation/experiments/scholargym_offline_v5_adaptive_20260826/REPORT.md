# V5 confidence-aware adaptive result-set experiment

## Protocol

- Frozen V3 candidates; no new API, LLM, retrieval, or reranker calls.
- Stratified deterministic split: dev 100, test 100, seed 2026.
- Thresholds were selected only by dev Macro F1; all final numbers below are held-out test results.
- Selected rule: maxK=2, minScore=0.60, minRatio=0.85, maxDrop=0.10.

## Held-out test results

| Method | Precision | Recall | Macro F1 | 95% CI | Avg. returned |
|---|---:|---:|---:|---:|---:|
| Fixed Top-1 | 0.3300 | 0.2241 | 0.2475 | [0.1715, 0.3255] | 1.000 |
| Fixed Top-2 | 0.1900 | 0.2537 | 0.1986 | [0.1424, 0.2537] | 2.000 |
| Fixed Top-3 | 0.1400 | 0.2697 | 0.1665 | [0.1219, 0.2105] | 3.000 |
| Fixed Top-5 | 0.0960 | 0.2926 | 0.1304 | [0.0991, 0.1627] | 5.000 |
| Adaptive | 0.3350 | 0.2374 | 0.2571 | [0.1812, 0.3350] | 1.070 |

## Interpretation boundary

Adaptive minus fixed Top-1 paired Macro F1 delta: 0.0097, 95% CI [0.0000, 0.0267].
The result is an offline selection ablation on a frozen candidate pool, not an official ScholarGym score. It does not by itself validate online evidence-gap expansion.
