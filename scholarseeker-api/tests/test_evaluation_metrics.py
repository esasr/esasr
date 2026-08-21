import unittest

from evaluation.metrics import evaluate_dataset, evaluate_query, paper_keys


class EvaluationMetricTests(unittest.TestCase):
    def test_matches_doi_across_url_and_prefixed_forms(self):
        self.assertTrue(
            paper_keys("doi:10.1000/example")
            & paper_keys({"doi": "https://doi.org/10.1000/EXAMPLE"})
        )

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


if __name__ == "__main__":
    unittest.main()
