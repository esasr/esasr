import unittest

from services.reranker_service import confidence_aware_select
from tools.calibrate_adaptive_selector import stratified_hash_split


class AdaptiveSelectorTests(unittest.TestCase):
    def test_selector_always_retains_top_one(self):
        rows = [{"relevanceScore": 0.2}, {"relevanceScore": 0.19}]
        selected = confidence_aware_select(
            rows, max_k=2, min_score=0.9, min_ratio=0.9, max_drop=0.01
        )
        self.assertEqual(selected, rows[:1])

    def test_selector_returns_contiguous_confident_prefix(self):
        rows = [
            {"relevanceScore": 0.8},
            {"relevanceScore": 0.7},
            {"relevanceScore": 0.3},
            {"relevanceScore": 0.29},
        ]
        selected = confidence_aware_select(
            rows, max_k=4, min_score=0.2, min_ratio=0.3, max_drop=0.25
        )
        self.assertEqual(selected, rows[:2])

    def test_stratified_split_is_deterministic_and_preserves_sources(self):
        gold = [
            {"id": f"a-{index}", "source": "A", "relevant": [str(index)]}
            for index in range(6)
        ] + [
            {"id": f"b-{index}", "source": "B", "relevant": [str(index)]}
            for index in range(4)
        ]
        first = stratified_hash_split(gold, 0.5, 2026)
        second = stratified_hash_split(gold, 0.5, 2026)
        self.assertEqual(first, second)
        dev, test = first
        self.assertEqual(len(dev), 5)
        self.assertEqual(len(test), 5)
        self.assertEqual({row["source"] for row in dev}, {"A", "B"})
        self.assertEqual({row["source"] for row in test}, {"A", "B"})


if __name__ == "__main__":
    unittest.main()
