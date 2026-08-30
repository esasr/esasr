import unittest
from unittest.mock import patch

from services.search_pipeline import (
    SearchBudget,
    analyze_coverage,
    attach_query_evidence,
    generate_evolution_queries,
    generate_gap_queries,
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
    def test_enforces_explicit_open_access_constraint(self):
        results = rank_and_merge(
            [
                (
                    "OpenAlex",
                    "transformer image matching",
                    [
                        {
                            "id": "closed",
                            "title": "Transformer Image Matching",
                            "abstract": "image matching with transformers",
                            "year": 2024,
                            "isOpenAccess": False,
                        },
                        {
                            "id": "open",
                            "title": "Open Transformer Image Matching",
                            "abstract": "image matching with transformers",
                            "year": 2024,
                            "isOpenAccess": True,
                        },
                    ],
                )
            ],
            _plan(year_from=None, year_to=None, open_source=True),
            10,
        )

        self.assertEqual([paper["id"] for paper in results], ["open"])

    def test_enforces_explicit_method_and_primary_topic(self):
        results = rank_and_merge(
            [
                (
                    "Semantic Scholar",
                    "Transformer image matching",
                    [
                        {
                            "id": "valid",
                            "title": "Transformer Image Matching",
                            "abstract": "Image matching with transformers.",
                            "year": 2024,
                        },
                        {
                            "id": "wrong-method",
                            "title": "Graph Image Matching",
                            "abstract": "Image matching with graph attention.",
                            "year": 2024,
                        },
                        {
                            "id": "wrong-topic",
                            "title": "Vision Transformers for Dense Prediction",
                            "abstract": "A transformer for semantic segmentation.",
                            "year": 2024,
                        },
                    ],
                )
            ],
            _plan(
                topics=["image matching"],
                methods=["Transformer"],
                methods_required=True,
                primary_topic_required=True,
                year_from=None,
                year_to=None,
            ),
            10,
        )

        self.assertEqual([paper["id"] for paper in results], ["valid"])

    def test_gap_queries_are_focused_and_do_not_repeat_long_question(self):
        plan = _plan(
            topics=["image matching"],
            methods=["Transformer"],
            datasets=["ScanNet", "MegaDepth"],
        )
        plan["research_question"] = "一段很长的中文复杂查询"
        plan["decomposed_queries"] = [
            "Transformer image matching low texture",
            "Transformer image matching ScanNet",
        ]
        queries = generate_gap_queries(
            plan,
            {
                "gaps": [
                    {"dimension": "datasets", "value": "MegaDepth"},
                    {"dimension": "year", "value": "2020–不限"},
                ]
            },
            ["Transformer image matching low texture"],
            3,
        )

        self.assertIn("Transformer image matching MegaDepth", queries)
        self.assertNotIn("一段很长的中文复杂查询", " ".join(queries))
        self.assertFalse(any("2020–不限" in query for query in queries))

    def test_preserves_record_provenance_over_retriever_label(self):
        results = rank_and_merge(
            [("OpenAlex", "rag", [{
                "id": "local_rag", "title": "Retrieval Augmented Generation",
                "abstract": "retrieval augmented generation", "source": "Offline Demo",
                "offline": True,
            }])],
            _plan(year_from=None, year_to=None),
            10,
        )

        self.assertEqual(results[0]["sources"], ["Offline Demo"])

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

    def test_evolves_query_from_repeated_new_result_terms(self):
        queries = generate_evolution_queries(
            _plan(),
            [
                {
                    "title": "Contrastive alignment for radiology",
                    "abstract": "Contrastive pretraining aligns image and report representations.",
                },
                {
                    "title": "Contrastive vision language pretraining",
                    "abstract": "Contrastive objectives improve clinical transfer.",
                },
            ],
            ["multimodal medical diagnosis"],
            2,
        )

        self.assertTrue(queries)
        self.assertTrue(any("contrastive" in query for query in queries))

    def test_attaches_criterion_level_evidence(self):
        papers = attach_query_evidence(
            _plan(methods=["cross encoder"], datasets=["MIMIC-CXR"]),
            [
                {
                    "id": "evidence",
                    "title": "Cross Encoder Diagnosis on MIMIC-CXR",
                    "abstract": (
                        "We train a cross encoder for multimodal medical diagnosis. "
                        "Experiments use the MIMIC-CXR dataset."
                    ),
                }
            ],
        )

        self.assertGreaterEqual(papers[0]["evidenceCoverage"], 0.5)
        self.assertIn("MIMIC-CXR", " ".join(papers[0]["evidence"]))
        self.assertTrue(all(item["source"] == "abstract" for item in papers[0]["criterionEvidence"]))


class SearchPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_precise_breadth_keeps_a_near_tied_top_cluster(self):
        async def retriever(_query, _limit):
            return [
                {"id": "a", "title": "A", "abstract": "multimodal diagnosis"},
                {"id": "b", "title": "B", "abstract": "multimodal diagnosis"},
                {"id": "c", "title": "C", "abstract": "multimodal diagnosis"},
            ]

        class StubReranker:
            model_name = "stub"

            def rerank(self, _query, papers, _top_n):
                scores = [0.90, 0.88, 0.50]
                return [
                    {**paper, "relevanceScore": score}
                    for paper, score in zip(papers, scores)
                ]

        result = await run_search_pipeline(
            "frozen query",
            limit=50,
            breadth_level=1,
            budget=SearchBudget(max_queries=2, max_api_calls=2, second_round_strategy="none"),
            retrievers={"mock": retriever},
            reranker=StubReranker(),
            reranker_metadata={
                "status": "configured",
                "topN": 3,
                "breadthSelector": {"enabled": True, "defaultLevel": 3},
            },
            plan_override=_plan(year_from=None, year_to=None),
        )

        self.assertEqual([paper["id"] for paper in result["papers"]], ["a", "b"])
        self.assertEqual(result["metrics"]["resultSelector"]["breadthLabel"], "精准")

    async def test_applies_calibrated_adaptive_selector_after_reranking(self):
        async def retriever(_query, _limit):
            return [
                {"id": "a", "title": "A", "abstract": "multimodal diagnosis"},
                {"id": "b", "title": "B", "abstract": "multimodal diagnosis"},
                {"id": "c", "title": "C", "abstract": "multimodal diagnosis"},
            ]

        class StubReranker:
            model_name = "stub"

            def rerank(self, _query, papers, _top_n):
                scores = [0.80, 0.70, 0.30]
                return [
                    {**paper, "relevanceScore": score}
                    for paper, score in zip(papers, scores)
                ]

        result = await run_search_pipeline(
            "frozen query",
            limit=10,
            budget=SearchBudget(max_queries=2, max_api_calls=2, second_round_strategy="none"),
            retrievers={"mock": retriever},
            reranker=StubReranker(),
            reranker_metadata={
                "status": "configured",
                "topN": 3,
                "adaptiveSelector": {
                    "enabled": True,
                    "maxK": 2,
                    "minScore": 0.60,
                    "minRatio": 0.85,
                    "maxDrop": 0.10,
                },
            },
            plan_override=_plan(year_from=None, year_to=None),
        )

        self.assertEqual([paper["id"] for paper in result["papers"]], ["a", "b"])
        self.assertEqual(result["metrics"]["reranker"]["adaptiveSelector"]["selected"], 2)

    async def test_can_disable_second_round_with_frozen_plan(self):
        calls = []

        async def retriever(query, limit):
            calls.append(query)
            return [{"id": query, "title": query, "abstract": query}]

        plan = _plan()
        result = await run_search_pipeline(
            "frozen query",
            budget=SearchBudget(
                max_queries=4,
                results_per_source=5,
                max_api_calls=8,
                second_round_strategy="none",
            ),
            retrievers={"mock": retriever},
            reranker_metadata={"status": "disabled"},
            plan_override=plan,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["plan"]["plannerMode"], "replay")
        self.assertFalse(result["coverage"]["secondRoundTriggered"])

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
        self.assertEqual(len(result["trace"]), 7)
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

    async def test_expands_citations_within_shared_api_budget(self):
        retrieval_calls = []
        citation_calls = []

        async def retriever(query: str, _limit: int):
            retrieval_calls.append(query)
            return [
                {
                    "id": "seed",
                    "title": "Multimodal Medical Diagnosis",
                    "abstract": "medical imaging diagnosis",
                    "year": 2024,
                }
            ]

        async def citation_expander(paper_id: str, _limit: int):
            citation_calls.append(paper_id)
            return [
                {
                    "id": "citation",
                    "title": "Vision Language Models for Medical Imaging",
                    "abstract": "multimodal medical diagnosis",
                    "year": 2023,
                }
            ]

        result = await run_search_pipeline(
            "multimodal models for medical diagnosis",
            limit=2,
            budget=SearchBudget(
                max_queries=1,
                results_per_source=5,
                max_api_calls=2,
                enable_citation_expansion=True,
                max_citation_seeds=1,
            ),
            retrievers={"OpenAlex": retriever},
            citation_expander=citation_expander,
            reranker_metadata={"status": "disabled"},
            plan_override=_plan(),
        )

        self.assertEqual(len(retrieval_calls), 1)
        self.assertEqual(citation_calls, ["seed"])
        self.assertEqual(result["metrics"]["apiCalls"], 2)
        self.assertEqual(result["metrics"]["citationSeeds"], ["seed"])
        self.assertEqual(result["metrics"]["sourceCounts"]["CitationGraph"], 1)

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
                reranker_metadata={"status": "configured", "topN": 2, "threshold": 0.95},
            )

        self.assertEqual(result["metrics"]["reranker"]["status"], "completed")
        self.assertEqual(result["metrics"]["reranker"]["model"], "fake-cross-encoder")
        self.assertEqual(result["metrics"]["reranker"]["selected"], 1)
        self.assertEqual(len(result["papers"]), 1)
        self.assertIn("crossEncoderScore", result["papers"][0])


if __name__ == "__main__":
    unittest.main()
