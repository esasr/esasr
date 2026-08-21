import unittest
from unittest.mock import AsyncMock, patch

from services.scholar_service import get_paper_details


class SemanticScholarDetailTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_search_snapshot_without_another_api_request(self):
        snapshot = {
            "id": "s2_abc",
            "title": "Learned Image Compression",
            "abstract": "A cached Semantic Scholar search result.",
        }
        with (
            patch(
                "services.scholar_service.cache_get",
                new=AsyncMock(return_value=snapshot),
            ),
            patch(
                "services.scholar_service._get_s2_paper",
                new=AsyncMock(),
            ) as remote,
        ):
            result = await get_paper_details("s2_abc")

        self.assertEqual(result, snapshot)
        remote.assert_not_awaited()

    async def test_returns_readable_temporary_state_after_rate_limit(self):
        with (
            patch(
                "services.scholar_service.cache_get",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "services.scholar_service._get_s2_paper",
                new=AsyncMock(side_effect=RuntimeError("429")),
            ),
        ):
            result = await get_paper_details("s2_abc")

        self.assertTrue(result["temporaryError"])
        self.assertNotIn("API Error", result["title"])


if __name__ == "__main__":
    unittest.main()
