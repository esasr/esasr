# ESASR experiment comparison (K=1)

| Run | F1@1 | 95% CI | Recall | Precision | MAP | nDCG | Tokens | API calls | Latency ms | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V1_title5 | 0.1862 | [0.1377, 0.2371] | 0.1745 | 0.2250 | 0.1745 | 0.2250 | 0.0 | 0.00 | 1000.9 | 0/200 |
| V2_equal_fields | 0.2466 | [0.1928, 0.3033] | 0.2301 | 0.3000 | 0.2301 | 0.3000 | 0.0 | 0.00 | 1022.3 | 0/200 |
| V3_cross_encoder | 0.2649 | [0.2093, 0.3223] | 0.2454 | 0.3300 | 0.2454 | 0.3300 | 0.0 | 0.00 | 741.7 | 0/200 |

F1 is the competition-facing set metric. MAP/nDCG diagnose ranking quality; Token, API-call, and latency columns must be checked before claiming an ablation gain under equal budget.
