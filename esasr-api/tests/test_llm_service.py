import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services.llm_service import (
    _extract_explicit_constraints,
    _fallback_plan,
    _heuristic_plan,
    _normalize_plan,
    analyze_search_query,
    plan_search_query,
    plan_search_query_uncached,
)


DEMO_QUERY = (
    "寻找 2020 年以来使用 Transformer 提升弱纹理或大视角变化场景下图像匹配性能的论文，"
    "要求发表于 CVPR、ICCV 或 ECCV 且可开放获取，优先包含 ScanNet 或 MegaDepth 实验，"
    "排除纯光流方法和综述文章。"
)


class KimiRequestOptionsTests(unittest.TestCase):
    def _response(self):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "research_question": "test",
                                "decomposed_queries": ["test"],
                                "constraints": {},
                            }
                        )
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
            model="test-model",
            system_fingerprint="test-fingerprint",
        )

    def test_kimi_k3_uses_low_reasoning_effort_without_temperature(self):
        settings = SimpleNamespace(
            base_url="https://api.moonshot.cn/v1",
            api_key="test-key",
            get=lambda key, default=None: 120 if key == "timeout" else default,
        )
        with (
            patch(
                "services.llm_service._provider_settings",
                return_value=("kimi", "kimi-k3", settings),
            ),
            patch("services.llm_service.OpenAI") as openai,
        ):
            openai.return_value.chat.completions.create.return_value = self._response()
            result = analyze_search_query("test query", "kimi", "kimi-k3")

        kwargs = openai.return_value.chat.completions.create.call_args.kwargs
        self.assertNotIn("temperature", kwargs)
        self.assertEqual(kwargs["reasoning_effort"], "low")
        self.assertEqual(kwargs["max_tokens"], 1200)
        self.assertEqual(result["model"], "kimi-k3")
        self.assertEqual(result["responseModel"], "test-model")

    def test_kimi_k26_disables_thinking_without_temperature(self):
        settings = SimpleNamespace(
            base_url="https://api.moonshot.cn/v1",
            api_key="test-key",
            get=lambda key, default=None: 120 if key == "timeout" else default,
        )

        with (
            patch(
                "services.llm_service._provider_settings",
                return_value=("kimi", "kimi-k2.6", settings),
            ),
            patch("services.llm_service.OpenAI") as openai,
        ):
            openai.return_value.chat.completions.create.return_value = self._response()
            analyze_search_query("test query", "kimi", "kimi-k2.6")

        kwargs = openai.return_value.chat.completions.create.call_args.kwargs
        self.assertNotIn("temperature", kwargs)
        self.assertEqual(
            kwargs["extra_body"],
            {"thinking": {"type": "disabled"}},
        )


class DeepSeekUsageTests(unittest.TestCase):
    def test_invalid_json_preserves_billed_usage_and_requests_json_output(self):
        settings = SimpleNamespace(
            base_url="https://api.deepseek.com",
            api_key="test-key",
            get=lambda key, default=None: 30 if key == "timeout" else default,
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"broken":'))],
            usage=SimpleNamespace(
                prompt_tokens=210,
                completion_tokens=1200,
                total_tokens=1410,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=900),
            ),
            model="deepseek-v4-flash",
            system_fingerprint="fp-test",
        )
        with (
            patch(
                "services.llm_service._provider_settings",
                return_value=("deepseek", "deepseek-v4-flash", settings),
            ),
            patch("services.llm_service.OpenAI") as openai,
        ):
            openai.return_value.chat.completions.create.return_value = response
            result = analyze_search_query(
                "compare transformers versus CNNs",
                "deepseek",
                "deepseek-v4-flash",
            )

        kwargs = openai.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(result["plannerMode"], "fallback")
        self.assertEqual(result["usage"]["total_tokens"], 1410)
        self.assertEqual(result["usage"]["reasoning_tokens"], 900)
        self.assertEqual(result["responseModel"], "deepseek-v4-flash")


class FallbackPlannerTests(unittest.TestCase):
    def test_extracts_complex_chinese_demo_query(self):
        constraints = _extract_explicit_constraints(DEMO_QUERY)

        self.assertIn("image matching", constraints["topics"])
        self.assertIn("Transformer", constraints["methods"])
        self.assertEqual(constraints["datasets"], ["ScanNet", "MegaDepth"])
        self.assertEqual(constraints["venues"], ["CVPR", "ICCV", "ECCV"])
        self.assertTrue(constraints["venues_required"])
        self.assertTrue(constraints["methods_required"])
        self.assertTrue(constraints["primary_topic_required"])
        self.assertEqual(constraints["year_from"], 2020)
        self.assertIsNone(constraints["year_to"])
        self.assertTrue(constraints["open_source"])
        self.assertIn("optical flow", constraints["exclude"])
        self.assertIn("survey", constraints["exclude"])

    def test_repairs_sparse_llm_plan_with_explicit_constraints(self):
        plan = _normalize_plan({"constraints": {}, "decomposed_queries": []}, DEMO_QUERY)

        self.assertTrue(plan["constraintRepair"]["applied"])
        self.assertEqual(plan["constraints"]["year_from"], 2020)
        self.assertIsNone(plan["constraints"]["year_to"])
        self.assertEqual(plan["constraints"]["venues"], ["CVPR", "ICCV", "ECCV"])
        self.assertTrue(plan["constraints"]["venues_required"])
        self.assertTrue(plan["constraints"]["methods_required"])
        self.assertTrue(plan["constraints"]["primary_topic_required"])
        self.assertGreaterEqual(len(plan["decomposed_queries"]), 3)
        self.assertTrue(all(query.isascii() for query in plan["decomposed_queries"]))
        self.assertNotIn(DEMO_QUERY, plan["constraints"]["topics"])

    def test_understands_recent_image_compression_top_venue_query(self):
        plan = _fallback_plan(
            "近三年关于图像压缩的顶会论文",
            "provider unavailable",
        )

        self.assertEqual(plan["constraints"]["topics"], ["image compression"])
        self.assertTrue(plan["constraints"]["venues_required"])
        self.assertIn("CVPR", plan["constraints"]["venues"])
        self.assertEqual(len(plan["decomposed_queries"]), 3)
        self.assertTrue(
            all("图像压缩" not in query for query in plan["decomposed_queries"])
        )
        self.assertIsNotNone(plan["constraints"]["year_from"])
        self.assertEqual(plan["fallbackReason"], "provider unavailable")

    def test_uses_local_plan_for_simple_english_topic(self):
        plan = _heuristic_plan("multimodal medical diagnosis 2024 open source")

        self.assertIsNotNone(plan)
        self.assertEqual(plan["plannerMode"], "heuristic")
        self.assertEqual(plan["usage"]["total_tokens"], 0)

    def test_uses_local_plan_for_fully_structured_chinese_request(self):
        plan = _heuristic_plan(DEMO_QUERY)

        self.assertIsNotNone(plan)
        self.assertEqual(plan["planner"], "deterministic-explicit")
        self.assertEqual(plan["plannerMode"], "heuristic")
        self.assertEqual(plan["usage"]["total_tokens"], 0)
        self.assertTrue(plan["constraints"]["methods_required"])

    def test_defers_complex_comparison_to_llm(self):
        self.assertIsNone(_heuristic_plan("compare transformers versus CNNs"))


class PlannerDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_uncached_planner_keeps_heuristic_routing_without_cache_io(self):
        with (
            patch("services.llm_service.cache_get", new=AsyncMock()) as cache_get,
            patch("services.llm_service.cache_set", new=AsyncMock()) as cache_set,
            patch("services.llm_service.analyze_search_query") as llm,
        ):
            plan = await plan_search_query_uncached(
                "image compression 2024 open source", "deepseek", "deepseek-v4-flash"
            )

        cache_get.assert_not_awaited()
        cache_set.assert_not_awaited()
        llm.assert_not_called()
        self.assertEqual(plan["plannerMode"], "heuristic")

    async def test_uncached_planner_calls_llm_for_complex_query(self):
        produced = {
            "research_question": "comparison",
            "decomposed_queries": ["comparison"],
            "constraints": {},
            "plannerMode": "llm",
            "usage": {"prompt_tokens": 200, "completion_tokens": 300, "total_tokens": 500},
        }
        with (
            patch("services.llm_service.cache_get", new=AsyncMock()) as cache_get,
            patch("services.llm_service.cache_set", new=AsyncMock()) as cache_set,
            patch(
                "services.llm_service.analyze_search_query",
                return_value=produced,
            ) as llm,
        ):
            plan = await plan_search_query_uncached(
                "compare transformers versus CNNs", "deepseek", "deepseek-v4-flash"
            )

        cache_get.assert_not_awaited()
        cache_set.assert_not_awaited()
        llm.assert_called_once()
        self.assertEqual(plan["usage"]["total_tokens"], 500)

    async def test_shared_cache_hit_has_zero_request_tokens(self):
        cached = {
            "research_question": "cached",
            "decomposed_queries": ["cached"],
            "constraints": {},
            "usage": {"prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100},
        }
        with patch(
            "services.llm_service.cache_get", new=AsyncMock(return_value=cached)
        ):
            plan = await plan_search_query("cached", "openai", "gpt-4o-mini")

        self.assertEqual(plan["plannerMode"], "cache")
        self.assertTrue(plan["cacheHit"])
        self.assertEqual(plan["usage"]["total_tokens"], 0)
        self.assertEqual(plan["originalUsage"]["total_tokens"], 100)

    async def test_heuristic_plan_skips_llm_and_is_cached(self):
        with (
            patch("services.llm_service.cache_get", new=AsyncMock(return_value=None)),
            patch("services.llm_service.cache_set", new=AsyncMock()) as cache_set,
            patch("services.llm_service.analyze_search_query") as llm,
        ):
            plan = await plan_search_query(
                "image compression 2024 open source", "openai", "gpt-4o-mini"
            )

        llm.assert_not_called()
        cache_set.assert_awaited_once()
        self.assertEqual(plan["plannerMode"], "heuristic")

    async def test_concurrent_requests_share_one_planning_task(self):
        release = asyncio.Event()
        produced = {
            "research_question": "shared",
            "decomposed_queries": ["shared"],
            "constraints": {},
            "plannerMode": "llm",
            "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
        }

        async def produce(*_args):
            await release.wait()
            return produced

        with (
            patch("services.llm_service.cache_get", new=AsyncMock(return_value=None)),
            patch("services.llm_service._produce_plan", new=AsyncMock(side_effect=produce)) as producer,
        ):
            first_task = asyncio.create_task(
                plan_search_query("shared query", "openai", "gpt-4o-mini")
            )
            await asyncio.sleep(0)
            second_task = asyncio.create_task(
                plan_search_query("shared query", "openai", "gpt-4o-mini")
            )
            await asyncio.sleep(0)
            release.set()
            first, second = await asyncio.gather(first_task, second_task)

        producer.assert_awaited_once()
        self.assertEqual(first["plannerMode"], "llm")
        self.assertEqual(second["plannerMode"], "coalesced")
        self.assertEqual(second["usage"]["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
