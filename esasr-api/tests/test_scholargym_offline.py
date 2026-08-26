import unittest

from tools.run_scholargym_offline import query_tokens, rrf_fuse, rule_routes, strip_abstracts


class ScholarGymOfflineTests(unittest.TestCase):
    def test_rule_routes_are_deterministic_and_fielded(self):
        first = rule_routes("Methods for hybrid reconstruction architectures")
        second = rule_routes("Methods for hybrid reconstruction architectures")
        self.assertEqual(first, second)
        self.assertEqual([route["name"] for route in first], ["title", "focused"])
        self.assertTrue(first[0]["match"].startswith("title : ("))
        self.assertIn(" AND ", first[1]["match"])

    def test_rrf_fusion_deduplicates_and_records_routes(self):
        fused = rrf_fuse(
            [
                ("original", 1.0, [{"arxivId": "A"}, {"arxivId": "B"}]),
                ("title", 0.5, [{"arxivId": "B"}, {"arxivId": "C"}]),
            ],
            rrf_k=10,
        )
        self.assertEqual([paper["arxivId"] for paper in fused], ["B", "A", "C"])
        self.assertEqual(fused[0]["retrievalRoutes"], ["original", "title"])

    def test_zero_weight_route_is_ignored(self):
        fused = rrf_fuse(
            [("original", 1.0, [{"arxivId": "A"}]), ("disabled", 0.0, [{"arxivId": "B"}])],
            rrf_k=30,
        )
        self.assertEqual([paper["arxivId"] for paper in fused], ["A"])

    def test_output_removes_large_abstract_payload(self):
        stripped = strip_abstracts([{"arxivId": "A", "title": "T", "abstract": "long"}])
        self.assertEqual(stripped, [{"arxivId": "A", "title": "T"}])

    def test_query_tokens_remove_request_boilerplate(self):
        self.assertEqual(
            query_tokens("Please provide papers about sparse attention transformers"),
            ["sparse", "attention", "transformers"],
        )


if __name__ == "__main__":
    unittest.main()
