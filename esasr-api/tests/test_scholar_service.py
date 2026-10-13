import unittest
from unittest.mock import AsyncMock, patch

from services.scholar_service import (
    _paper_summary,
    get_citation_graph,
    get_mock_papers,
    get_paper_details,
)


class ProvenanceTests(unittest.TestCase):
    def test_missing_openalex_metadata_is_not_fabricated(self):
        summary = _paper_summary({"id": "https://openalex.org/W1", "title": "Example"})

        self.assertIsNone(summary["year"])
        self.assertEqual(summary["relevanceScore"], 0)
        self.assertIn("year", summary["metadataMissing"])
        self.assertIn("doi", summary["metadataMissing"])

    def test_offline_fallback_is_explicitly_labelled(self):
        result = get_mock_papers("retrieval augmented generation")[0]

        self.assertTrue(result["offline"])
        self.assertEqual(result["source"], "Offline Demo")
        self.assertEqual(result["dataSourceStatus"], "offline_fallback")


class CitationGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_related_edges_are_not_labelled_as_citations(self):
        graph = await get_citation_graph("local_rag")

        self.assertTrue(graph["edges"])
        self.assertTrue(all(edge["type"] == "RELATED" for edge in graph["edges"]))


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
