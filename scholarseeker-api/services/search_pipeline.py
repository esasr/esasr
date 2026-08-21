"""Budget-aware, coverage-driven academic retrieval orchestration."""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable

from config import cfg
from redis_db import cache_set
from services.llm_service import plan_search_query
from services.reranker_service import PaperReranker, get_configured_reranker
from services.scholar_service import search_papers
from services.semantic_scholar_client import get_json as semantic_scholar_get_json


PaperRetriever = Callable[[str, int], Awaitable[list[dict]]]

_VENUE_ALIASES = {
    "cvpr": ("computer vision and pattern recognition",),
    "iccv": ("international conference on computer vision",),
    "eccv": ("european conference on computer vision",),
    "neurips": (
        "neural information processing systems",
        "advances in neural information processing systems",
    ),
    "iclr": ("international conference on learning representations",),
    "icml": ("international conference on machine learning",),
    "aaai": ("aaai conference on artificial intelligence",),
    "acm multimedia": ("acm multimedia", "acm international conference on multimedia"),
    "dcc": ("data compression conference",),
    "pcs": ("picture coding symposium",),
    "icip": ("international conference on image processing",),
}


@dataclass(frozen=True)
class SearchBudget:
    max_queries: int = 4
    results_per_source: int = 15
    max_api_calls: int = 8


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w+#.-]{2,}", (text or "").casefold())
        if token not in {
            "the", "and", "for", "with", "from", "using", "based", "paper",
            "papers", "research", "study", "about", "关于", "研究", "论文", "方法", "应用",
        }
    }


def _unique_text(values: list[str], limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).split()).strip()
        if not cleaned or cleaned.casefold() in seen:
            continue
        seen.add(cleaned.casefold())
        result.append(cleaned)
        if limit and len(result) >= limit:
            break
    return result


def _canonical_key(paper: dict) -> str:
    doi = str(paper.get("doi") or "").casefold().replace("https://doi.org/", "").strip()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"\W+", "", str(paper.get("title") or "").casefold())
    return f"title:{title[:180]}" if title else f"id:{paper.get('id')}"


def _venue_matches(paper_venue: str, allowed_venues: list[str]) -> bool:
    normalized = " ".join(str(paper_venue or "").casefold().split())
    for allowed in allowed_venues:
        key = str(allowed).casefold().strip()
        # “Top conference” means the main proceedings. APIs often return CVPRW
        # and similarly named workshop venues, which must not pass via a loose
        # acronym substring match.
        if (
            any(marker in normalized for marker in ("workshop", "workshops", "cvprw"))
            and not any(marker in key for marker in ("workshop", "workshops", "cvprw"))
        ):
            continue
        candidates = (key, *_VENUE_ALIASES.get(key, ()))
        if any(candidate in normalized for candidate in candidates):
            return True
    return False


def _semantic_scholar_summary(item: dict) -> dict:
    external_ids = item.get("externalIds") or {}
    authors = ", ".join(author.get("name", "") for author in item.get("authors") or [])
    pdf = item.get("openAccessPdf") or {}
    return {
        "id": f"s2_{item.get('paperId')}",
        "sourceId": item.get("paperId"),
        "title": item.get("title") or "Untitled",
        "authors": authors or "Unknown authors",
        "venue": item.get("venue") or "Preprint",
        "year": item.get("year"),
        "abstract": item.get("abstract") or "No abstract available.",
        "citationCount": item.get("citationCount") or 0,
        "isOpenAccess": bool(pdf.get("url")),
        "pdfUrl": pdf.get("url") or "",
        "doi": external_ids.get("DOI") or "",
        "url": item.get("url") or "",
        "source": "Semantic Scholar",
    }


async def search_semantic_scholar(query: str, limit: int) -> list[dict]:
    settings = cfg.semantic_scholar
    fields = (
        "paperId,title,authors,venue,year,abstract,citationCount,"
        "openAccessPdf,externalIds,url"
    )
    try:
        data = await semantic_scholar_get_json(
            "/paper/search",
            {"query": query, "limit": min(limit, 100), "fields": fields},
        )
        papers = [_semantic_scholar_summary(item) for item in data.get("data", [])]
        ttl = cfg.redis.ttl.get("paper_detail", 3600)
        await asyncio.gather(
            *[
                cache_set(f"paper_detail:{paper['id']}", paper, ttl=ttl)
                for paper in papers
            ]
        )
        return papers
    except Exception as exc:
        print(f"[Semantic Scholar Error] query={query!r}: {exc}")
        return []


def rank_and_merge(
    ranked_lists: list[tuple[str, str, list[dict]]],
    plan: dict,
    limit: int,
) -> list[dict]:
    """Fuse source rankings with RRF, constraints, lexical evidence and authority."""
    candidates: dict[str, dict] = {}
    accumulators: dict[str, dict] = defaultdict(
        lambda: {"rrf": 0.0, "queries": set(), "sources": set()}
    )

    for source, query, papers in ranked_lists:
        for rank, incoming in enumerate(papers, start=1):
            key = _canonical_key(incoming)
            current = candidates.get(key)
            if current is None or len(incoming.get("abstract") or "") > len(current.get("abstract") or ""):
                candidates[key] = {**(current or {}), **incoming}
            accumulators[key]["rrf"] += 1.0 / (60 + rank)
            accumulators[key]["queries"].add(query)
            accumulators[key]["sources"].add(source)

    query_terms = _tokens(
        " ".join(
            [plan.get("research_question", "")]
            + plan.get("constraints", {}).get("topics", [])
            + plan.get("constraints", {}).get("methods", [])
            + plan.get("constraints", {}).get("datasets", [])
        )
    )
    constraints = plan.get("constraints", {})
    year_from, year_to = constraints.get("year_from"), constraints.get("year_to")
    allowed_venues = [
        str(venue).strip()
        for venue in constraints.get("venues", [])
        if str(venue).strip()
    ]
    exclusions = [_tokens(value) for value in constraints.get("exclude", [])]
    max_rrf = max((value["rrf"] for value in accumulators.values()), default=1.0)

    results: list[dict] = []
    for key, paper in candidates.items():
        year = paper.get("year")
        if year_from and year and int(year) < int(year_from):
            continue
        if year_to and year and int(year) > int(year_to):
            continue
        if constraints.get("venues_required") and allowed_venues:
            if not _venue_matches(paper.get("venue") or "", allowed_venues):
                continue

        searchable = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        paper_terms = _tokens(searchable)
        if any(excluded and excluded <= paper_terms for excluded in exclusions):
            continue

        matched_terms = sorted(query_terms & paper_terms)
        lexical = len(matched_terms) / max(1, min(len(query_terms), 12))
        source_agreement = min(1.0, len(accumulators[key]["sources"]) / 2)
        query_coverage = min(
            1.0,
            len(accumulators[key]["queries"])
            / max(1, min(len(plan.get("decomposed_queries", [])), 3)),
        )
        authority = min(1.0, math.log1p(paper.get("citationCount") or 0) / math.log(10001))
        rrf = accumulators[key]["rrf"] / max_rrf
        score = (
            0.48 * rrf
            + 0.25 * lexical
            + 0.12 * query_coverage
            + 0.10 * source_agreement
            + 0.05 * authority
        )

        sources = sorted(accumulators[key]["sources"])
        matched_queries = sorted(accumulators[key]["queries"])
        evidence = matched_terms[:6]
        results.append(
            {
                **paper,
                "canonicalKey": key,
                "sources": sources,
                "matchedQueries": matched_queries,
                "matchedTerms": evidence,
                "relevanceScore": round(min(score, 1.0), 4),
                "relevanceLevel": "高度相关" if score >= 0.62 else "部分相关",
                "recommendReason": (
                    f"命中 {', '.join(evidence[:4]) or '核心检索语义'}；"
                    f"由 {len(matched_queries)} 个子查询、{len(sources)} 个数据源共同召回。"
                ),
            }
        )

    results.sort(
        key=lambda paper: (
            paper["relevanceScore"],
            len(paper.get("sources", [])),
            paper.get("citationCount") or 0,
        ),
        reverse=True,
    )
    return results[:limit]


def analyze_coverage(plan: dict, papers: list[dict], min_hits: int = 2) -> dict:
    """Measure whether each explicit query constraint is represented by candidates."""
    constraints = plan.get("constraints", {})
    dimensions: list[dict] = []
    searchable_papers = [
        (
            _tokens(f"{paper.get('title', '')} {paper.get('abstract', '')}"),
            str(paper.get("venue") or "").casefold(),
            paper,
        )
        for paper in papers
    ]

    for dimension in ("topics", "methods", "datasets", "domains"):
        for value in constraints.get(dimension, []) or []:
            expected = _tokens(value)
            if not expected:
                continue
            required_overlap = max(1, math.ceil(len(expected) * 0.5))
            hits = sum(
                1
                for paper_terms, _, _ in searchable_papers
                if len(expected & paper_terms) >= required_overlap
            )
            dimensions.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "hits": hits,
                    "covered": hits >= min_hits,
                }
            )

    venues = constraints.get("venues", []) or []
    if venues:
        hits = sum(
            1
            for _, paper_venue, _ in searchable_papers
            if _venue_matches(paper_venue, venues)
        )
        dimensions.append(
            {
                "dimension": "venues",
                "value": " / ".join(str(venue) for venue in venues),
                "hits": hits,
                "covered": hits >= 1,
            }
        )

    year_from, year_to = constraints.get("year_from"), constraints.get("year_to")
    if year_from or year_to:
        hits = sum(
            1
            for _, _, paper in searchable_papers
            if paper.get("year")
            and (not year_from or int(paper["year"]) >= int(year_from))
            and (not year_to or int(paper["year"]) <= int(year_to))
        )
        dimensions.append(
            {
                "dimension": "year",
                "value": f"{year_from or '不限'}–{year_to or '不限'}",
                "hits": hits,
                "covered": hits >= 1,
            }
        )

    if constraints.get("open_source") is True:
        hits = sum(1 for _, _, paper in searchable_papers if paper.get("isOpenAccess"))
        dimensions.append(
            {
                "dimension": "open_source",
                "value": "open source",
                "hits": hits,
                "covered": hits >= 1,
            }
        )

    gaps = [item for item in dimensions if not item["covered"]]
    covered = len(dimensions) - len(gaps)
    return {
        "score": round(covered / len(dimensions), 4) if dimensions else 1.0,
        "covered": covered,
        "total": len(dimensions),
        "dimensions": dimensions,
        "gaps": gaps,
    }


def generate_gap_queries(
    plan: dict,
    coverage: dict,
    used_queries: list[str],
    limit: int,
) -> list[str]:
    """Create focused second-round queries without another LLM call."""
    if limit <= 0:
        return []
    research_question = plan.get("research_question", "")
    gap_queries = [
        f"{research_question} {gap['value']}"
        for gap in coverage.get("gaps", [])
        if gap.get("value")
    ]
    planned_queries = plan.get("decomposed_queries", [])
    used = {query.casefold() for query in used_queries}
    return [
        query
        for query in _unique_text(gap_queries + planned_queries)
        if query.casefold() not in used
    ][:limit]


async def _retrieve_round(
    queries: list[str],
    retrievers: dict[str, PaperRetriever],
    results_per_source: int,
    max_api_calls: int,
) -> dict:
    tasks: list[tuple[str, str, Awaitable[list[dict]]]] = []
    for subquery in queries:
        for source, retriever in retrievers.items():
            if len(tasks) >= max_api_calls:
                break
            tasks.append((source, subquery, retriever(subquery, results_per_source)))

    started = time.perf_counter()
    responses = await asyncio.gather(
        *(task[2] for task in tasks),
        return_exceptions=True,
    )
    ranked_lists: list[tuple[str, str, list[dict]]] = []
    source_counts: dict[str, int] = defaultdict(int)
    failures: list[str] = []
    for (source, subquery, _), response in zip(tasks, responses):
        if isinstance(response, Exception):
            failures.append(f"{source}: {type(response).__name__}")
            continue
        papers = response or []
        source_counts[source] += len(papers)
        ranked_lists.append((source, subquery, papers))
    return {
        "rankedLists": ranked_lists,
        "apiCalls": len(tasks),
        "sourceCounts": dict(source_counts),
        "failures": failures,
        "durationMs": round((time.perf_counter() - started) * 1000),
    }


async def run_search_pipeline(
    query: str,
    limit: int = 20,
    budget: SearchBudget | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    retrievers: dict[str, PaperRetriever] | None = None,
    reranker: PaperReranker | None = None,
    reranker_metadata: dict | None = None,
) -> dict:
    started = time.perf_counter()
    budget = budget or SearchBudget()
    retrievers = retrievers or {
        "OpenAlex": search_papers,
        "Semantic Scholar": search_semantic_scholar,
    }

    planner_started = time.perf_counter()
    plan = await plan_search_query(query, llm_provider, llm_model)
    planner_ms = round((time.perf_counter() - planner_started) * 1000)
    all_queries = _unique_text(plan.get("decomposed_queries") or [query], budget.max_queries)
    first_queries = all_queries[: min(2, budget.max_queries)]

    first_round = await _retrieve_round(
        first_queries,
        retrievers,
        budget.results_per_source,
        budget.max_api_calls,
    )
    ranked_lists = list(first_round["rankedLists"])
    source_counts: dict[str, int] = defaultdict(int, first_round["sourceCounts"])
    failures = list(first_round["failures"])
    if plan.get("fallbackReason"):
        failures.insert(0, f"查询规划已降级：{plan['fallbackReason']}")
    api_calls = first_round["apiCalls"]

    candidate_pool_size = min(100, max(limit * 3, 30))
    first_candidates = rank_and_merge(ranked_lists, plan, candidate_pool_size)
    first_coverage = analyze_coverage(plan, first_candidates)
    needs_second_round = bool(first_coverage["gaps"]) or len(first_candidates) < limit

    remaining_queries = max(0, budget.max_queries - len(first_queries))
    second_queries = generate_gap_queries(
        plan,
        first_coverage,
        first_queries,
        remaining_queries,
    ) if needs_second_round else []
    remaining_calls = max(0, budget.max_api_calls - api_calls)
    second_round = {
        "rankedLists": [],
        "apiCalls": 0,
        "sourceCounts": {},
        "failures": [],
        "durationMs": 0,
    }
    if second_queries and remaining_calls:
        second_round = await _retrieve_round(
            second_queries,
            retrievers,
            budget.results_per_source,
            remaining_calls,
        )
        ranked_lists.extend(second_round["rankedLists"])
        api_calls += second_round["apiCalls"]
        failures.extend(second_round["failures"])
        for source, count in second_round["sourceCounts"].items():
            source_counts[source] += count

    candidates = rank_and_merge(ranked_lists, plan, candidate_pool_size)
    final_coverage = analyze_coverage(plan, candidates)

    if reranker_metadata is None:
        configured_reranker, reranker_metadata = get_configured_reranker()
        reranker = reranker or configured_reranker
    reranker_metadata = dict(reranker_metadata or {})
    rerank_started = time.perf_counter()
    if reranker is not None:
        try:
            configured_top_n = int(reranker_metadata.get("topN", 40))
            top_n = max(limit, min(configured_top_n, len(candidates)))
            candidates = await asyncio.to_thread(
                reranker.rerank,
                plan.get("research_question") or query,
                candidates,
                top_n,
            )
            reranker_metadata.update(
                {
                    "status": "completed",
                    "model": getattr(reranker, "model_name", reranker_metadata.get("model", "")),
                    "reranked": len(candidates),
                }
            )
        except Exception as exc:
            reranker_metadata.update(
                {
                    "status": "fallback",
                    "detail": str(exc),
                    "reranked": 0,
                }
            )
            failures.append(f"Cross Encoder: {type(exc).__name__}")
    papers = candidates[: max(1, min(limit, 50))]
    rerank_ms = round((time.perf_counter() - rerank_started) * 1000)
    total_ms = round((time.perf_counter() - started) * 1000)
    raw_candidates = sum(source_counts.values())

    trace = [
        {
            "stage": "查询规划",
            "status": "degraded" if plan.get("fallbackReason") else "completed",
            "detail": (
                f"大模型不可用，已由本地规则生成 {len(all_queries)} 个检索子查询"
                if plan.get("fallbackReason")
                else (
                    f"命中共享规划缓存，复用 {len(all_queries)} 个检索子查询"
                    if plan.get("plannerMode") == "cache"
                    else (
                        f"本地规则生成 {len(all_queries)} 个检索子查询，未调用大模型"
                        if plan.get("plannerMode") == "heuristic"
                        else (
                            f"合并并复用并发规划，获得 {len(all_queries)} 个检索子查询"
                            if plan.get("plannerMode") == "coalesced"
                            else f"大模型生成 {len(all_queries)} 个检索子查询"
                        )
                    )
                )
            ),
            "durationMs": planner_ms,
        },
        {
            "stage": "首轮多源召回",
            "status": "completed" if first_round["rankedLists"] else "degraded",
            "detail": f"{len(first_queries)} 个查询，获得 {sum(first_round['sourceCounts'].values())} 条结果",
            "durationMs": first_round["durationMs"],
        },
        {
            "stage": "覆盖度诊断",
            "status": "completed",
            "detail": (
                f"覆盖 {first_coverage['covered']}/{first_coverage['total']} 个约束，"
                f"发现 {len(first_coverage['gaps'])} 个缺口"
            ),
            "durationMs": 0,
        },
        {
            "stage": "缺口补检",
            "status": "completed" if second_round["apiCalls"] else "skipped",
            "detail": (
                f"新增 {len(second_queries)} 个查询，获得 "
                f"{sum(second_round['sourceCounts'].values())} 条结果"
                if second_round["apiCalls"]
                else "首轮覆盖充分或检索预算已耗尽"
            ),
            "durationMs": second_round["durationMs"],
        },
        {
            "stage": "Cross Encoder 精排",
            "status": reranker_metadata.get("status", "disabled"),
            "detail": (
                f"{reranker_metadata.get('model', '未配置')}；"
                f"精排 {reranker_metadata.get('reranked', 0)} 篇"
            ),
            "durationMs": rerank_ms,
        },
        {
            "stage": "结果输出",
            "status": "completed",
            "detail": f"去重后输出 {len(papers)} 篇论文，最终覆盖率 {final_coverage['score']:.0%}",
            "durationMs": max(
                0,
                total_ms
                - planner_ms
                - first_round["durationMs"]
                - second_round["durationMs"]
                - rerank_ms,
            ),
        },
    ]

    return {
        "query": query,
        "plan": plan,
        "papers": papers,
        "coverage": {
            "firstRound": first_coverage,
            "final": final_coverage,
            "secondRoundTriggered": bool(second_round["apiCalls"]),
            "secondRoundQueries": second_queries if second_round["apiCalls"] else [],
        },
        "trace": trace,
        "metrics": {
            "apiCalls": api_calls,
            "llmTokens": plan.get("usage", {}).get("total_tokens", 0),
            "llmPromptTokens": plan.get("usage", {}).get("prompt_tokens", 0),
            "llmCompletionTokens": plan.get("usage", {}).get("completion_tokens", 0),
            "llmReasoningTokens": plan.get("usage", {}).get("reasoning_tokens", 0),
            "plannerMode": plan.get("plannerMode", "llm"),
            "plannerCacheHit": bool(plan.get("cacheHit", False)),
            "plannerCoalesced": bool(plan.get("coalesced", False)),
            "sourceCounts": dict(source_counts),
            "rawCandidates": raw_candidates,
            "returnedPapers": len(papers),
            "totalDurationMs": total_ms,
            "failures": failures,
            "reranker": reranker_metadata,
            "budget": {
                "maxQueries": budget.max_queries,
                "resultsPerSource": budget.results_per_source,
                "maxApiCalls": budget.max_api_calls,
            },
        },
    }
