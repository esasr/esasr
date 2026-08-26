import unittest

from evaluation.metrics import (
    evaluate_cutoffs,
    evaluate_dataset,
    evaluate_query,
    paired_bootstrap_delta,
    paper_keys,
)


class EvaluationMetricTests(unittest.TestCase):
    def test_matches_doi_across_url_and_prefixed_forms(self):
        self.assertTrue(
            paper_keys("doi:10.1000/example")
            & paper_keys({"doi": "https://doi.org/10.1000/EXAMPLE"})
        )

    def test_matches_arxiv_across_dataset_api_and_doi_forms(self):
        expected = paper_keys({"arxivId": "1901.00137"})
        self.assertTrue(expected & paper_keys("arxiv:1901.00137"))
        self.assertTrue(expected & paper_keys("https://arxiv.org/abs/1901.00137v2"))
        self.assertTrue(expected & paper_keys({"doi": "10.48550/arXiv.1901.00137"}))

    def test_computes_query_f1_at_k(self):
        result = evaluate_query(
            relevant=[{"id": "A"}, {"id": "B"}],
            predicted=[{"id": "A"}, {"id": "X"}, {"id": "B"}],
            k=2,
        )
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["f1"], 0.5)

    def test_reports_macro_micro_and_missing_predictions(self):
        report = evaluate_dataset(
            [
                {"id": "q1", "relevant": [{"id": "A"}]},
                {"id": "q2", "relevant": [{"id": "B"}]},
            ],
            [{"id": "q1", "predicted": [{"id": "A"}]}],
            k=20,
        )
        self.assertEqual(report["missingPredictions"], ["q2"])
        self.assertEqual(report["macro"]["f1"], 0.5)
        self.assertEqual(report["micro"]["recall"], 0.5)

    def test_reports_rank_metrics_and_duplicate_predictions(self):
        result = evaluate_query(
            relevant=[{"id": "A"}, {"id": "B"}],
            predicted=[{"id": "X"}, {"id": "A"}, {"id": "A"}, {"id": "B"}],
            k=4,
        )
        self.assertEqual(result["reciprocalRank"], 0.5)
        self.assertEqual(result["averagePrecision"], 0.5)
        self.assertGreater(result["ndcg"], 0)
        self.assertEqual(result["duplicatePredictions"], 1)

    def test_graded_relevance_changes_ndcg(self):
        relevant = [{"id": "A", "relevance": 2}, {"id": "B", "relevance": 1}]
        ideal = evaluate_query(relevant, [{"id": "A"}, {"id": "B"}], k=2)
        reversed_order = evaluate_query(relevant, [{"id": "B"}, {"id": "A"}], k=2)
        self.assertEqual(ideal["ndcg"], 1.0)
        self.assertLess(reversed_order["ndcg"], ideal["ndcg"])

    def test_reports_constraints_structure_and_efficiency(self):
        report = evaluate_dataset(
            [
                {
                    "id": "q1",
                    "constraints": {"year_from": 2024, "venues": ["ACL"]},
                    "relevant": [{"id": "A"}],
                }
            ],
            [
                {
                    "id": "q1",
                    "constraints": {"year_from": 2024, "venues": ["ACL"]},
                    "predicted": [
                        {
                            "id": "A",
                            "title": "Paper A",
                            "authors": ["Author"],
                            "year": 2024,
                            "venue": "ACL",
                            "source": "openalex",
                            "evidence": ["matched method"],
                        }
                    ],
                    "trace": [{"stage": "planning"}],
                    "graph": {"nodes": [{"id": "A"}], "edges": []},
                    "metrics": {"apiCalls": 4, "llmTokens": 120, "totalDurationMs": 800},
                }
            ],
            bootstrap_samples=20,
            seed=7,
        )
        self.assertEqual(report["constraints"]["f1"], 1.0)
        self.assertEqual(report["structure"]["paperFieldCoverage"], 1.0)
        self.assertEqual(report["structure"]["evidenceCoverage"], 1.0)
        self.assertEqual(report["efficiency"]["apiCalls"]["mean"], 4.0)
        self.assertEqual(report["efficiency"]["llmTokens"]["perTruePositive"], 120.0)
        self.assertEqual(report["reliability"]["failureRate"], 0.0)

    def test_reports_rate_limit_failures_separately_from_quality(self):
        report = evaluate_dataset(
            [{"id": "q1", "relevant": [{"id": "A"}]}],
            [{"id": "q1", "predicted": [{"id": "A"}], "metrics": {"failures": ["Semantic Scholar: HTTPStatusError"]}}],
            bootstrap_samples=10,
        )
        self.assertEqual(report["macro"]["f1"], 1.0)
        self.assertEqual(report["reliability"]["failedQueries"], 1)
        self.assertEqual(report["reliability"]["failureRate"], 1.0)
        self.assertEqual(report["reliability"]["failureEvents"], 1)

    def test_multiple_cutoffs_and_deterministic_intervals(self):
        gold = [{"id": "q1", "relevant": [{"id": "A"}, {"id": "B"}]}]
        predictions = [{"id": "q1", "predicted": [{"id": "A"}, {"id": "B"}]}]
        first = evaluate_cutoffs(gold, predictions, [1, 2], bootstrap_samples=25, seed=9)
        second = evaluate_cutoffs(gold, predictions, [1, 2], bootstrap_samples=25, seed=9)
        self.assertEqual(set(first), {"1", "2"})
        self.assertLess(first["1"]["macro"]["recall"], first["2"]["macro"]["recall"])
        self.assertEqual(first["2"]["macroConfidenceIntervals"], second["2"]["macroConfidenceIntervals"])

    def test_reports_group_slices_and_prediction_id_issues(self):
        report = evaluate_dataset(
            [
                {"id": "q1", "domain": "medicine", "difficulty": "hard", "relevant": [{"id": "A"}]},
                {"id": "q2", "domain": "cs", "difficulty": "easy", "relevant": [{"id": "B"}]},
            ],
            [
                {"id": "q1", "predicted": [{"id": "A"}]},
                {"id": "q1", "predicted": [{"id": "X"}]},
                {"id": "q3", "predicted": []},
            ],
            bootstrap_samples=10,
        )
        self.assertEqual(report["duplicatePredictionIds"], ["q1"])
        self.assertEqual(report["extraPredictionIds"], ["q3"])
        self.assertEqual(report["groups"]["domain"]["medicine"]["queries"], 1)
        self.assertEqual(report["groups"]["difficulty"]["easy"]["macro"]["f1"], 0.0)

    def test_paired_bootstrap_delta(self):
        baseline = [{"id": "q1", "f1": 0.2}, {"id": "q2", "f1": 0.4}]
        candidate = [{"id": "q1", "f1": 0.4}, {"id": "q2", "f1": 0.5}]
        result = paired_bootstrap_delta(baseline, candidate, samples=50, seed=3)
        self.assertEqual(result["queries"], 2)
        self.assertEqual(result["delta"], 0.15)
        self.assertEqual(result["winRate"], 1.0)


if __name__ == "__main__":
    unittest.main()
