import unittest
from unittest.mock import patch

from services.search_pipeline import (
    SearchBudget,
    analyze_coverage,
    rank_and_merge,
    run_search_pipeline,
)


def _plan(**constraint_overrides):
    constraints = {
        "topics": ["multimodal medical diagnosis"],
        "methods": [],
        "datasets": [],
        "domains": ["medical imaging"],
        "venues": [],
        "exclude": [],
        "year_from": 2022,
        "year_to": 2026,
        "open_source": None,
        **constraint_overrides,
    }
    return {
        "research_question": "multimodal models for medical diagnosis",
        "intentions": [{"label": "Topic", "value": "multimodal medical diagnosis"}],
        "constraints": constraints,
        "decomposed_queries": [
            "multimodal medical diagnosis",
            "vision language model medical imaging",
            "medical foundation model diagnosis",
        ],
        "ambiguities": [],
        "planner": "test",
    }


class RankAndMergeTests(unittest.TestCase):
    def test_deduplicates_by_doi_and_records_multi_source_evidence(self):
        openalex = {
            "id": "W1",
            "title": "Multimodal Models for Medical Diagnosis",
            "abstract": "A multimodal model for diagnosis in medical imaging.",
            "year": 2024,
            "citationCount": 50,
            "doi": "10.1000/example",
            "source": "OpenAlex",
        }
        semantic_scholar = {
            **openalex,
            "id": "s2_1",
            "abstract": "A longer multimodal model abstract for diagnosis in medical imaging.",
            "source": "Semantic Scholar",
        }

        results = rank_and_merge(
            [
                ("OpenAlex", "multimodal medical diagnosis", [openalex]),
                ("Semantic Scholar", "multimodal medical diagnosis", [semantic_scholar]),
            ],
            _plan(),
            10,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["sources"], ["OpenAlex", "Semantic Scholar"])
        self.assertIn("multimodal", results[0]["matchedTerms"])
        self.assertGreater(results[0]["relevanceScore"], 0.5)

    def test_applies_year_and_exclusion_constraints(self):
        results = rank_and_merge(
            [
                (
                    "OpenAlex",
                    "medical imaging",
                    [
                        {
                            "id": "old",
                            "title": "Medical Imaging",
                            "abstract": "multimodal diagnosis",
                            "year": 2019,
                        },
                        {
                            "id": "survey",
                            "title": "A Survey of Multimodal Medical Imaging",
                            "abstract": "diagnosis",
                            "year": 2024,
                        },
                        {
                            "id": "valid",
                            "title": "Multimodal Medical Diagnosis",
                            "abstract": "medical imaging foundation model",
                            "year": 2024,
                        },
                    ],
                )
            ],
            _plan(exclude=["survey"]),
            10,
        )

        self.assertEqual([paper["id"] for paper in results], ["valid"])

    def test_reports_uncovered_explicit_constraints(self):
        coverage = analyze_coverage(
            _plan(methods=["cross encoder"], datasets=["MIMIC-CXR"]),
            [
                {
                    "title": "Multimodal Models for Medical Diagnosis",
                    "abstract": "A multimodal medical imaging diagnosis system.",
                    "year": 2024,
                },
                {
                    "title": "Medical Vision Language Models",
                    "abstract": "Multimodal diagnosis for medical imaging.",
                    "year": 2024,
                },
            ],
        )

        self.assertEqual(
            {(gap["dimension"], gap["value"]) for gap in coverage["gaps"]},
            {("methods", "cross encoder"), ("datasets", "MIMIC-CXR")},
        )

    def test_treats_configured_venues_as_or_constraint(self):
        plan = _plan(
            venues=["CVPR", "ICCV", "ECCV"],
            venues_required=True,
        )
        results = rank_and_merge(
            [
                (
                    "OpenAlex",
                    "image compression",
                    [
                        {
                            "id": "cvpr",
                            "title": "Learned Image Compression",
                            "abstract": "neural image compression",
                            "venue": "Computer Vision and Pattern Recognition",
                            "year": 2025,
                        },
                        {
                            "id": "nature",
                            "title": "Learned Image Compression",
                            "abstract": "neural image compression",
                            "venue": "Nature",
                            "year": 2025,
                        },
                        {
                            "id": "cvpr-workshop",
                            "title": "Learned Image Compression Workshop Paper",
                            "abstract": "neural image compression",
                            "venue": (
                                "2025 IEEE/CVF Conference on Computer Vision and "
                                "Pattern Recognition Workshops (CVPRW)"
                            ),
                            "year": 2025,
                        },
                    ],
                )
            ],
            plan,
            10,
        )

        self.assertEqual([paper["id"] for paper in results], ["cvpr"])
        coverage = analyze_coverage(plan, results, min_hits=1)
        self.assertNotIn("venues", {gap["dimension"] for gap in coverage["gaps"]})


class SearchPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_selected_llm_provider_to_query_planner(self):
        async def retriever(_query: str, _limit: int):
            return []

        with patch(
            "services.search_pipeline.plan_search_query",
            return_value=_plan(),
        ) as planner:
            await run_search_pipeline(
                "multimodal models for medical diagnosis",
                limit=1,
                budget=SearchBudget(max_queries=1, results_per_source=5, max_api_calls=1),
                llm_provider="kimi",
                llm_model="moonshot-v1-8k",
                retrievers={"OpenAlex": retriever},
            )

        planner.assert_awaited_once_with(
            "multimodal models for medical diagnosis",
            "kimi",
            "moonshot-v1-8k",
        )

    async def test_respects_api_call_budget_and_returns_trace(self):
        calls: list[tuple[str, str]] = []

        def retriever(source: str):
            async def search(query: str, limit: int):
                calls.append((source, query))
                return [
                    {
                        "id": f"{source}-{len(calls)}",
                        "title": f"Multimodal Medical Diagnosis {source}",
                        "abstract": "medical imaging diagnosis",
                        "year": 2024,
                        "source": source,
                    }
                ]

            return search

        with patch("services.search_pipeline.plan_search_query", return_value=_plan()):
            result = await run_search_pipeline(
                "multimodal models for medical diagnosis",
                limit=10,
                budget=SearchBudget(
                    max_queries=3,
                    results_per_source=5,
                    max_api_calls=3,
                ),
                retrievers={
                    "OpenAlex": retriever("OpenAlex"),
                    "Semantic Scholar": retriever("Semantic Scholar"),
                },
            )

        self.assertEqual(len(calls), 3)
        self.assertEqual(result["metrics"]["apiCalls"], 3)
        self.assertEqual(len(result["trace"]), 6)
        self.assertGreaterEqual(len(result["papers"]), 1)

    async def test_uses_second_round_to_fill_a_coverage_gap(self):
        calls: list[str] = []

        async def retriever(query: str, _limit: int):
            calls.append(query)
            if "MIMIC-CXR" in query:
                return [
                    {
                        "id": f"gap-{len(calls)}",
                        "title": f"Multimodal Diagnosis on MIMIC-CXR {len(calls)}",
                        "abstract": "Medical imaging diagnosis using the MIMIC-CXR dataset.",
                        "year": 2024,
                    }
                ]
            return [
                {
                    "id": f"base-{len(calls)}",
                    "title": "Multimodal Medical Diagnosis",
                    "abstract": "Medical imaging diagnosis.",
                    "year": 2024,
                }
            ]

        plan = _plan(datasets=["MIMIC-CXR"])
        with patch("services.search_pipeline.plan_search_query", return_value=plan):
            result = await run_search_pipeline(
                "multimodal models for medical diagnosis",
                limit=2,
                budget=SearchBudget(max_queries=4, results_per_source=5, max_api_calls=8),
                retrievers={"OpenAlex": retriever, "Semantic Scholar": retriever},
            )

        self.assertTrue(result["coverage"]["secondRoundTriggered"])
        self.assertTrue(any("MIMIC-CXR" in query for query in result["coverage"]["secondRoundQueries"]))
        self.assertEqual(result["coverage"]["final"]["gaps"], [])

    async def test_applies_injected_cross_encoder_reranker(self):
        class FakeReranker:
            model_name = "fake-cross-encoder"

            def rerank(self, _query: str, papers: list[dict], top_n: int):
                selected = list(reversed(papers[:top_n]))
                return [
                    {
                        **paper,
                        "crossEncoderScore": 0.99 - index * 0.1,
                        "relevanceScore": 0.99 - index * 0.1,
                    }
                    for index, paper in enumerate(selected)
                ]

        async def retriever(_query: str, _limit: int):
            return [
                {
                    "id": "first",
                    "title": "Multimodal Medical Diagnosis A",
                    "abstract": "medical imaging diagnosis",
                    "year": 2024,
                },
                {
                    "id": "second",
                    "title": "Multimodal Medical Diagnosis B",
                    "abstract": "medical imaging diagnosis",
                    "year": 2024,
                },
            ]

        with patch("services.search_pipeline.plan_search_query", return_value=_plan()):
            result = await run_search_pipeline(
                "multimodal models for medical diagnosis",
                limit=2,
                budget=SearchBudget(max_queries=1, results_per_source=5, max_api_calls=1),
                retrievers={"OpenAlex": retriever},
                reranker=FakeReranker(),
                reranker_metadata={"status": "configured", "topN": 2},
            )

        self.assertEqual(result["metrics"]["reranker"]["status"], "completed")
        self.assertEqual(result["metrics"]["reranker"]["model"], "fake-cross-encoder")
        self.assertIn("crossEncoderScore", result["papers"][0])


if __name__ == "__main__":
    unittest.main()
