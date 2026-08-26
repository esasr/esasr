import unittest

from routers.search import _validate_llm, list_llm_providers


class LocalPlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_planner_is_always_available(self):
        payload = await list_llm_providers()

        self.assertEqual(payload["providers"][0]["id"], "local")
        self.assertEqual(payload["providers"][0]["models"], ["heuristic"])

    def test_local_planner_needs_no_api_key(self):
        self.assertEqual(_validate_llm("local", "heuristic"), (None, None))


if __name__ == "__main__":
    unittest.main()
