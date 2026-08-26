# ESASR experiment comparison (K=20)

| Run | F1@20 | 95% CI | Recall | Precision | MAP | nDCG | Tokens | API calls | Latency ms | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 0.0417 | [0.0000, 0.0833] | 0.2778 | 0.0228 | 0.1944 | 0.2271 | 581.8 | 1.00 | 5806.4 | 0/9 |
| C0 | 0.0346 | [0.0000, 0.0668] | 0.2778 | 0.0185 | 0.1889 | 0.2222 | 581.8 | 3.11 | 9034.4 | 0/9 |
| C1 | 0.0346 | [0.0000, 0.0668] | 0.2778 | 0.0185 | 0.1944 | 0.2271 | 581.8 | 5.33 | 21276.4 | 1/9 |
| D | 0.0346 | [0.0000, 0.0668] | 0.2778 | 0.0185 | 0.1889 | 0.2222 | 581.8 | 3.56 | 11792.1 | 0/9 |

F1 is the competition-facing set metric. MAP/nDCG diagnose ranking quality; Token, API-call, and latency columns must be checked before claiming an ablation gain under equal budget.
