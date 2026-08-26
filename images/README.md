# ESASR report figure registry

All newly generated academic figures use the same deep-blue, orange-red, gray-white palette and an original layout. Each figure is exported as PNG (report embedding), SVG (editable source), and PDF (vector QA).

| Figure stem | Method / purpose | Used in |
|---|---|---|
| `Fig1_ESASR_OverallFramework` | Overall evidence-state adaptive retrieval framework | Main report |
| `Fig2_CQC_QueryCompiler` | Constraint-aware query compiler | Main report |
| `Fig3_EGRR_RetrievalRouting` | Evidence-gap retrieval routing | Main report |
| `Fig4_MEFR_LCER_RankingPipeline` | Evidence fusion and local cross-encoder reranking | Main report |
| `Fig5_CARS_AdaptiveSelection` | Confidence-gated adaptive result selection | Main report |
| `Fig6_System_EndToEndDataFlow` | End-to-end system data flow and trust boundary | Main report |
| `Fig7_Experiment_EvidenceProtocol` | Two-level experimental evidence protocol | Main report |
| `Fig8_Ablation_Performance` | Measured ablation and output-policy comparison | Main report and technical record |
| `Fig9_Deployment_Topology` | Container deployment and secret isolation | Main report |
| `Fig10_Iteration_Roadmap` | Iteration and decision history | Technical record only |

Regenerate with `esasr-api/venv/bin/python tools/generate_report_figures.py`.
