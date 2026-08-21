import asyncio
import copy
import hashlib
import json
import re
from datetime import datetime

from openai import OpenAI

from config import cfg
from redis_db import cache_get, cache_set


_llm = cfg.llm
_PLANNER_CACHE_VERSION = "v2"
_planner_tasks: dict[str, asyncio.Task] = {}
_planner_tasks_lock: asyncio.Lock | None = None
_planner_loop: asyncio.AbstractEventLoop | None = None
_TOP_IMAGE_VENUES = [
    "CVPR", "ICCV", "ECCV", "NeurIPS", "ICLR", "ICML",
    "AAAI", "ACM Multimedia", "DCC", "PCS", "ICIP",
]


def _provider_settings(provider: str | None = None, model: str | None = None):
    provider_name = provider or _llm.active_provider
    if provider_name not in _llm.providers:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
    if not _llm.is_provider_configured(provider_name):
        raise ValueError(f"LLM provider is not configured: {provider_name}")
    settings = _llm.get_provider(provider_name)
    model_name = model or settings.get("model", "")
    if model_name not in _llm.provider_models(provider_name):
        raise ValueError(f"Unsupported model for {provider_name}: {model_name}")
    return provider_name, model_name, settings


def _unique_text(values: list[str], limit: int = 6) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split()).strip()
        if cleaned and cleaned.casefold() not in {item.casefold() for item in result}:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _fallback_plan(user_query: str, reason: str = "") -> dict:
    """Return a usable plan even when the configured LLM is unavailable."""
    current_year = datetime.now().year
    normalized_query = " ".join(user_query.split()).strip()
    query_lower = normalized_query.casefold()
    years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", user_query)]
    year_from = min(years) if years else None
    year_to = max(years) if years else None

    recent_match = re.search(r"(?:近|最近)\s*([一二两三四五六七八九十\d]+)\s*年", user_query)
    if recent_match and not years:
        chinese_numbers = {
            "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        }
        raw = recent_match.group(1)
        count = int(raw) if raw.isdigit() else chinese_numbers.get(raw)
        if count:
            year_from, year_to = current_year - count + 1, current_year

    open_source = True if any(
        marker in query_lower
        for marker in ("开源", "公开代码", "open source", "github", "代码")
    ) else None

    is_image_compression = "图像压缩" in normalized_query or "image compression" in query_lower
    is_lossy = "有损" in normalized_query or "lossy" in query_lower
    wants_top_venues = any(
        marker in query_lower
        for marker in ("顶会", "顶级会议", "top conference", "top-tier conference")
    )
    if is_image_compression:
        topic = "lossy image compression" if is_lossy else "image compression"
        decomposed_queries = [
            topic,
            f"learned {topic} neural compression",
            f"{topic} CVPR ICCV ECCV NeurIPS",
        ]
        topic_label = "有损图像压缩" if is_lossy else "图像压缩"
    else:
        topic = normalized_query
        decomposed_queries = [normalized_query]
        topic_label = normalized_query

    venues = _TOP_IMAGE_VENUES if wants_top_venues and is_image_compression else []
    intentions = [{"label": "Topic", "value": topic_label}]
    if year_from or year_to:
        intentions.append({
            "label": "Year",
            "value": f"{year_from or '不限'}–{year_to or '不限'}",
        })
    if wants_top_venues:
        intentions.append({"label": "Venue", "value": "顶级会议"})

    plan = {
        "research_question": user_query,
        "intentions": intentions,
        "constraints": {
            "topics": [topic],
            "methods": [],
            "datasets": [],
            "domains": [],
            "venues": venues,
            "venues_required": bool(venues),
            "exclude": [],
            "year_from": year_from,
            "year_to": year_to,
            "open_source": open_source,
        },
        "decomposed_queries": _unique_text(decomposed_queries),
        "ambiguities": [],
        "planner": "heuristic-fallback",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    if reason:
        plan["fallbackReason"] = reason
    return plan


def _heuristic_plan(user_query: str) -> dict | None:
    """Return a local plan only when the query is safe to use verbatim."""
    normalized = " ".join(user_query.split()).strip()
    lowered = normalized.casefold()
    complex_markers = (
        " compare ", " versus ", " vs ", " except ", " excluding ",
        " but not ", "区别", "比较", "对比", "除外", "排除", "以及", "同时",
    )
    if any(marker in f" {lowered} " for marker in complex_markers):
        return None

    is_image_compression = "图像压缩" in normalized or "image compression" in lowered
    is_short_english_topic = (
        normalized.isascii()
        and len(normalized.split()) <= 14
        and not re.search(r"[?!;:]", normalized)
    )
    if not (is_image_compression or is_short_english_topic):
        return None

    plan = _fallback_plan(normalized)
    plan["planner"] = "heuristic"
    plan["plannerMode"] = "heuristic"
    plan["cacheHit"] = False
    plan["coalesced"] = False
    return plan


def _intentions_from_constraints(constraints: dict, user_query: str) -> list[dict]:
    labels = (
        ("topics", "Topic"), ("methods", "Method"),
        ("datasets", "Dataset"), ("domains", "Domain"),
        ("venues", "Venue"),
    )
    intentions = [
        {"label": label, "value": " / ".join(values)}
        for key, label in labels
        if (values := constraints.get(key))
    ]
    year_from, year_to = constraints.get("year_from"), constraints.get("year_to")
    if year_from or year_to:
        intentions.append({
            "label": "Year",
            "value": f"{year_from or '不限'}–{year_to or '不限'}",
        })
    if constraints.get("open_source") is not None:
        intentions.append({
            "label": "Open Source",
            "value": "是" if constraints["open_source"] else "否",
        })
    return intentions or [{"label": "Topic", "value": user_query}]


def _normalize_plan(raw: dict, user_query: str) -> dict:
    fallback = _fallback_plan(user_query)
    constraints = raw.get("constraints") if isinstance(raw.get("constraints"), dict) else raw

    normalized_constraints = {
        "topics": _unique_text(constraints.get("topics") or [user_query]),
        "methods": _unique_text(constraints.get("methods") or []),
        "datasets": _unique_text(constraints.get("datasets") or []),
        "domains": _unique_text(constraints.get("domains") or []),
        "venues": _unique_text(constraints.get("venues") or []),
        "venues_required": bool(constraints.get("venues_required", False)),
        "exclude": _unique_text(constraints.get("exclude") or []),
        "year_from": constraints.get("year_from"),
        "year_to": constraints.get("year_to"),
        "open_source": constraints.get("open_source"),
    }
    for key in ("year_from", "year_to"):
        value = normalized_constraints[key]
        try:
            normalized_constraints[key] = int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            normalized_constraints[key] = None

    planned_queries = list(
        raw.get("decomposed_queries") or raw.get("sub_queries") or []
    )
    subqueries = _unique_text(
        planned_queries + [user_query] if planned_queries else [user_query],
        limit=6,
    )
    intentions = raw.get("intentions")
    if not isinstance(intentions, list):
        intentions = _intentions_from_constraints(normalized_constraints, user_query)
    intentions = [
        {"label": str(item.get("label", "")), "value": str(item.get("value", ""))}
        for item in intentions
        if isinstance(item, dict) and item.get("value")
    ]

    return {
        "research_question": str(raw.get("research_question") or user_query),
        "intentions": intentions or fallback["intentions"],
        "constraints": normalized_constraints,
        "decomposed_queries": subqueries,
        "ambiguities": _unique_text(raw.get("ambiguities") or []),
        "planner": raw.get("planner") or f"llm:{_llm.model}",
    }


def analyze_search_query(
    user_query: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    provider_name = provider or _llm.active_provider
    model_name = model or ""
    prompt = f"""Convert this academic search request into JSON; do not answer it or
invent constraints. Use English retrieval terms and at most 5 queries.
Request: {json.dumps(user_query, ensure_ascii=False)}
Schema: {{"decomposed_queries":["query"],"topics":[],"methods":[],
"datasets":[],"domains":[],"venues":[],"venues_required":false,
"exclude":[],"year_from":null,"year_to":null,"open_source":null}}
Preserve all explicit constraints. Output JSON only."""
    try:
        provider_name, model_name, settings = _provider_settings(provider, model)
        client = OpenAI(base_url=settings.base_url, api_key=settings.api_key)
        request_options = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Plan high-recall academic searches. Return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "timeout": int(settings.get("timeout", 30)),
            "max_tokens": int(settings.get("max_output_tokens", 500)),
        }
        if provider_name == "kimi" and model_name.startswith("kimi-k"):
            # Current Kimi models require their fixed sampling parameters.
            # K3 always thinks; low effort is sufficient for query planning.
            if model_name == "kimi-k3":
                request_options["reasoning_effort"] = "low"
            elif model_name == "kimi-k2.6":
                request_options["extra_body"] = {
                    "thinking": {"type": "disabled"}
                }
        else:
            request_options["temperature"] = 0
        response = client.chat.completions.create(**request_options)
        content = response.choices[0].message.content or "{}"
        content = content.replace("```json", "").replace("```", "").strip()
        raw = json.loads(content)
        if not isinstance(raw, dict):
            raise ValueError("planner response must be an object")
        plan = _normalize_plan(raw, user_query)
        plan["planner"] = f"llm:{provider_name}/{model_name}"
        plan["provider"] = provider_name
        plan["model"] = model_name
        usage = response.usage
        details = getattr(usage, "completion_tokens_details", None)
        plan["usage"] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            "reasoning_tokens": getattr(details, "reasoning_tokens", 0) or 0,
        }
        plan["plannerMode"] = "llm"
        plan["cacheHit"] = False
        plan["coalesced"] = False
        return plan
    except Exception as exc:
        print(f"[LLM Planner Error] provider={provider_name} model={model_name}: {exc}")
        plan = _fallback_plan(user_query, str(exc))
        plan["provider"] = provider_name
        plan["model"] = model_name
        plan["plannerMode"] = "fallback"
        plan["cacheHit"] = False
        plan["coalesced"] = False
        return plan


def _planner_cache_key(user_query: str, provider: str | None, model: str | None) -> str:
    provider_name = provider or _llm.active_provider
    settings = _llm.providers.get(provider_name, {})
    model_name = model or settings.get("model", "")
    normalized = " ".join(user_query.split()).strip().casefold()
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"query_plan:{_PLANNER_CACHE_VERSION}:{provider_name}:{model_name}:{digest}"


def _delivery_copy(plan: dict, mode: str, *, cache_hit: bool, coalesced: bool) -> dict:
    delivered = copy.deepcopy(plan)
    if mode != "llm":
        delivered["originalUsage"] = delivered.get("usage", {})
        delivered["usage"] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "reasoning_tokens": 0,
        }
    delivered["plannerMode"] = mode
    delivered["cacheHit"] = cache_hit
    delivered["coalesced"] = coalesced
    return delivered


async def _produce_plan(
    user_query: str,
    provider: str | None,
    model: str | None,
    cache_key: str,
) -> dict:
    plan = _heuristic_plan(user_query)
    if plan is None:
        plan = await asyncio.to_thread(analyze_search_query, user_query, provider, model)
    ttl = int(cfg.redis.ttl.get("query_plan", 86400))
    if not plan.get("fallbackReason"):
        await cache_set(cache_key, plan, ttl=ttl)
    return plan


async def plan_search_query(
    user_query: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """Plan with shared caching, conservative local rules and in-flight deduplication."""
    cache_key = _planner_cache_key(user_query, provider, model)
    cached = await cache_get(cache_key)
    if isinstance(cached, dict):
        return _delivery_copy(cached, "cache", cache_hit=True, coalesced=False)

    global _planner_tasks_lock, _planner_loop
    loop = asyncio.get_running_loop()
    if _planner_tasks_lock is None or _planner_loop is not loop:
        _planner_tasks.clear()
        _planner_tasks_lock = asyncio.Lock()
        _planner_loop = loop
    async with _planner_tasks_lock:
        task = _planner_tasks.get(cache_key)
        coalesced = task is not None
        if task is None:
            task = asyncio.create_task(_produce_plan(user_query, provider, model, cache_key))
            _planner_tasks[cache_key] = task
    try:
        plan = await task
    finally:
        if not coalesced:
            async with _planner_tasks_lock:
                _planner_tasks.pop(cache_key, None)

    if coalesced:
        return _delivery_copy(plan, "coalesced", cache_hit=False, coalesced=True)
    return copy.deepcopy(plan)
