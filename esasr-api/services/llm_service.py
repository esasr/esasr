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
_PLANNER_CACHE_VERSION = "v4"
_planner_tasks: dict[str, asyncio.Task] = {}
_planner_tasks_lock: asyncio.Lock | None = None
_planner_loop: asyncio.AbstractEventLoop | None = None
_TOP_IMAGE_VENUES = [
    "CVPR", "ICCV", "ECCV", "NeurIPS", "ICLR", "ICML",
    "AAAI", "ACM Multimedia", "DCC", "PCS", "ICIP",
]

_KNOWN_VENUES = (
    "CVPR", "ICCV", "ECCV", "NeurIPS", "ICLR", "ICML", "AAAI",
    "IJCAI", "ACL", "EMNLP", "NAACL", "ACM Multimedia", "ICIP",
)
_KNOWN_METHODS = (
    "Transformer", "Cross Encoder", "BM25", "RRF", "LLM",
    "Vision Transformer", "Diffusion Model",
)
_KNOWN_DATASETS = (
    "ScanNet", "MegaDepth", "ImageNet", "COCO", "KITTI", "MIMIC-CXR",
    "CheXpert", "MS MARCO",
)


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


def _extract_explicit_constraints(user_query: str) -> dict:
    """Extract high-confidence slots before or after LLM planning.

    This parser is intentionally conservative: it only records terms explicitly
    present in the request and translates a small set of retrieval concepts into
    the English vocabulary expected by OpenAlex and Semantic Scholar.
    """
    normalized = " ".join(user_query.split()).strip()
    lowered = normalized.casefold()

    years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", normalized)]
    year_from = min(years) if years else None
    year_to = max(years) if years else None
    since_year = re.search(
        r"(?:自|从)?\s*((?:19|20)\d{2})\s*年?\s*(?:以来|以后|之后|起)",
        normalized,
    ) or re.search(r"\b(?:since|after)\s+((?:19|20)\d{2})\b", lowered)
    if since_year:
        year_from = int(since_year.group(1))
        year_to = None
    year_detected = bool(years or since_year)

    venues = [
        venue for venue in _KNOWN_VENUES
        if re.search(rf"(?<![A-Za-z]){re.escape(venue)}(?![A-Za-z])", normalized, re.I)
    ]
    methods = [
        method for method in _KNOWN_METHODS
        if re.search(rf"(?<![A-Za-z]){re.escape(method)}(?![A-Za-z])", normalized, re.I)
    ]
    datasets = [
        dataset for dataset in _KNOWN_DATASETS
        if re.search(rf"(?<![A-Za-z]){re.escape(dataset)}(?![A-Za-z])", normalized, re.I)
    ]

    topics: list[str] = []
    domains: list[str] = []
    if "图像匹配" in normalized or "image matching" in lowered:
        topics.append("image matching")
        domains.append("computer vision")
    if any(marker in normalized for marker in ("局部特征匹配", "特征匹配")):
        topics.append("local feature matching")
    if "弱纹理" in normalized or "low texture" in lowered or "low-texture" in lowered:
        topics.append("low-texture image matching")
    if "大视角" in normalized or "large viewpoint" in lowered or "wide baseline" in lowered:
        topics.append("large viewpoint change image matching")

    exclusions: list[str] = []
    if any(marker in normalized for marker in ("纯光流", "光流方法")) or "optical flow" in lowered:
        exclusions.append("optical flow")
    if "综述" in normalized or any(marker in lowered for marker in ("survey article", "review article")):
        exclusions.extend(["survey", "review"])

    open_access_markers = (
        "开放获取", "公开获取", "可公开获取", "open access", "open-access",
    )
    open_source_markers = ("开源", "公开代码", "open source", "github")
    open_source_detected = any(marker in lowered for marker in (*open_access_markers, *open_source_markers))
    open_source = True if open_source_detected else None
    venues_required = bool(
        venues
        and re.search(r"要求.*(?:发表于|发表)|仅限|必须|must|published\s+in", normalized, re.I)
    )
    methods_required = bool(
        methods
        and re.search(
            r"(?:使用|采用|基于|运用)\s*[A-Za-z-]*\s*Transformer|"
            r"\b(?:using|with|based\s+on)\s+(?:a\s+)?Transformer\b",
            normalized,
            re.I,
        )
    )
    primary_topic_required = bool(
        topics
        and ("图像匹配" in normalized or "image matching" in lowered)
    )

    return {
        "topics": _unique_text(topics),
        "methods": _unique_text(methods),
        "datasets": _unique_text(datasets),
        "domains": _unique_text(domains),
        "venues": _unique_text(venues),
        "venues_required": venues_required,
        "methods_required": methods_required,
        "primary_topic_required": primary_topic_required,
        "exclude": _unique_text(exclusions),
        "year_from": year_from,
        "year_to": year_to,
        "open_source": open_source,
        "_year_detected": year_detected,
        "_open_source_detected": open_source_detected,
    }


def _explicit_retrieval_queries(user_query: str, constraints: dict) -> list[str]:
    """Build concise English API queries from explicitly extracted slots."""
    methods = constraints.get("methods") or []
    topics = constraints.get("topics") or []
    datasets = constraints.get("datasets") or []
    if not (methods or topics or datasets):
        return []

    method = methods[0] if methods else ""
    base_topic = topics[0] if topics else ""
    challenge_terms: list[str] = []
    lowered = user_query.casefold()
    if "弱纹理" in user_query or "low texture" in lowered or "low-texture" in lowered:
        challenge_terms.append("low texture")
    if "大视角" in user_query or "large viewpoint" in lowered or "wide baseline" in lowered:
        challenge_terms.append("large viewpoint change")

    candidates = [" ".join([method, base_topic, *challenge_terms])]
    if datasets:
        candidates.append(" ".join([method, "local feature matching", *datasets]))
        candidates.extend(" ".join([method, base_topic, dataset]) for dataset in datasets)
    if constraints.get("venues"):
        candidates.append(" ".join([method, base_topic, *constraints["venues"]]))
    return _unique_text(candidates, limit=5)


def _fallback_plan(user_query: str, reason: str = "") -> dict:
    """Return a usable plan even when the configured LLM is unavailable."""
    current_year = datetime.now().year
    normalized_query = " ".join(user_query.split()).strip()
    query_lower = normalized_query.casefold()
    explicit = _extract_explicit_constraints(user_query)
    year_from = explicit["year_from"]
    year_to = explicit["year_to"]

    recent_match = re.search(r"(?:近|最近)\s*([一二两三四五六七八九十\d]+)\s*年", user_query)
    if recent_match and not explicit["_year_detected"]:
        chinese_numbers = {
            "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        }
        raw = recent_match.group(1)
        count = int(raw) if raw.isdigit() else chinese_numbers.get(raw)
        if count:
            year_from, year_to = current_year - count + 1, current_year

    open_source = explicit["open_source"] if explicit["_open_source_detected"] else (True if any(
        marker in query_lower
        for marker in ("开源", "公开代码", "open source", "github", "代码")
    ) else None)

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
        topic = explicit["topics"][0] if explicit["topics"] else normalized_query
        decomposed_queries = _explicit_retrieval_queries(user_query, explicit) or [normalized_query]
        topic_label = topic

    venues = explicit["venues"] or (
        _TOP_IMAGE_VENUES if wants_top_venues and is_image_compression else []
    )
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
            "topics": explicit["topics"] or [topic],
            "methods": explicit["methods"],
            "datasets": explicit["datasets"],
            "domains": explicit["domains"],
            "venues": venues,
            "venues_required": explicit["venues_required"] or bool(
                wants_top_venues and venues
            ),
            "methods_required": explicit["methods_required"],
            "primary_topic_required": explicit["primary_topic_required"],
            "exclude": explicit["exclude"],
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
    """Return a local plan when explicit slots make interpretation unambiguous."""
    normalized = " ".join(user_query.split()).strip()
    lowered = normalized.casefold()
    explicit = _extract_explicit_constraints(normalized)
    structured_explicit = bool(
        explicit["topics"]
        and explicit["methods"]
        and (explicit["venues"] or explicit["datasets"])
        and explicit["_year_detected"]
    )
    complex_markers = (
        " compare ", " versus ", " vs ", " except ", " excluding ",
        " but not ", "区别", "比较", "对比", "除外", "排除", "以及", "同时",
    )
    if not structured_explicit and any(
        marker in f" {lowered} " for marker in complex_markers
    ):
        return None

    is_image_compression = "图像压缩" in normalized or "image compression" in lowered
    is_short_english_topic = (
        normalized.isascii()
        and len(normalized.split()) <= 14
        and not re.search(r"[?!;:]", normalized)
    )
    if not (structured_explicit or is_image_compression or is_short_english_topic):
        return None

    plan = _fallback_plan(normalized)
    plan["planner"] = "deterministic-explicit" if structured_explicit else "heuristic"
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
    explicit = _extract_explicit_constraints(user_query)
    constraints = raw.get("constraints") if isinstance(raw.get("constraints"), dict) else raw

    raw_topics = _unique_text(constraints.get("topics") or [])
    if explicit["topics"]:
        raw_topics = [topic for topic in raw_topics if topic.casefold() != user_query.casefold()]

    normalized_constraints = {
        "topics": _unique_text(explicit["topics"] + raw_topics) or [user_query],
        "methods": _unique_text(explicit["methods"] + list(constraints.get("methods") or [])),
        "datasets": _unique_text(explicit["datasets"] + list(constraints.get("datasets") or [])),
        "domains": _unique_text(explicit["domains"] + list(constraints.get("domains") or [])),
        "venues": _unique_text(explicit["venues"] + list(constraints.get("venues") or [])),
        "venues_required": bool(
            explicit["venues_required"] or constraints.get("venues_required", False)
        ),
        "methods_required": bool(
            explicit["methods_required"] or constraints.get("methods_required", False)
        ),
        "primary_topic_required": bool(
            explicit["primary_topic_required"]
            or constraints.get("primary_topic_required", False)
        ),
        "exclude": _unique_text(explicit["exclude"] + list(constraints.get("exclude") or [])),
        "year_from": explicit["year_from"] if explicit["_year_detected"] else constraints.get("year_from"),
        "year_to": explicit["year_to"] if explicit["_year_detected"] else constraints.get("year_to"),
        "open_source": explicit["open_source"] if explicit["_open_source_detected"] else constraints.get("open_source"),
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
    explicit_queries = _explicit_retrieval_queries(user_query, explicit)
    if explicit_queries:
        planned_queries = [
            query for query in planned_queries
            if " ".join(str(query).split()).casefold() != user_query.casefold()
        ]
    subqueries = _unique_text(
        explicit_queries + planned_queries + ([] if explicit_queries else [user_query]),
        limit=6,
    )
    intentions = _intentions_from_constraints(normalized_constraints, user_query)

    repaired_fields = [
        key for key in (
            "topics", "methods", "datasets", "domains", "venues", "exclude",
            "methods_required", "primary_topic_required",
            "year_from", "year_to", "open_source",
        )
        if explicit.get(key) not in (None, [], False)
    ]

    return {
        "research_question": str(raw.get("research_question") or user_query),
        "intentions": intentions or fallback["intentions"],
        "constraints": normalized_constraints,
        "decomposed_queries": subqueries,
        "ambiguities": _unique_text(raw.get("ambiguities") or []),
        "planner": raw.get("planner") or f"llm:{_llm.model}",
        "constraintRepair": {
            "applied": bool(repaired_fields),
            "fields": repaired_fields,
            "source": "deterministic-explicit-parser",
        },
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
            "max_tokens": max(1200, int(settings.get("max_output_tokens", 1200))),
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
