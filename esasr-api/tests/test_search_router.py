import unittest

from routers.search import FullSearchRequest, _validate_llm, list_llm_providers


class LocalPlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_planner_is_always_available(self):
        payload = await list_llm_providers()

        self.assertEqual(payload["providers"][0]["id"], "local")
        self.assertEqual(payload["providers"][0]["models"], ["heuristic"])

    def test_local_planner_needs_no_api_key(self):
        self.assertEqual(_validate_llm("local", "heuristic"), (None, None))

    def test_full_search_accepts_five_confidence_breadth_levels(self):
        precise = FullSearchRequest(query="multimodal retrieval", breadth_level=1)
        broad = FullSearchRequest(query="multimodal retrieval", breadth_level=5)
        self.assertEqual(precise.breadth_level, 1)
        self.assertEqual(broad.breadth_level, 5)


if __name__ == "__main__":
    unittest.main()
