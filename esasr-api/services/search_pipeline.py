"""Budget-aware, coverage-driven academic retrieval orchestration."""

from __future__ import annotations

import asyncio
import copy
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable

from config import cfg
from redis_db import cache_set
from services.calibrated_evidence import calibrated_base_score, egrr_decision
from services.llm_service import plan_search_query
from services.reranker_service import (
    PaperReranker,
    confidence_aware_select,
    confidence_mass_select,
    get_configured_reranker,
)
from services.scholar_service import get_related_papers, search_papers
from services.semantic_scholar_client import get_json as semantic_scholar_get_json


PaperRetriever = Callable[[str, int], Awaitable[list[dict]]]
CitationExpander = Callable[[str, int], Awaitable[list[dict]]]


async def _search_openalex_strict(query: str, limit: int) -> list[dict]:
    """Keep demo fallbacks out of scored multi-source retrieval."""
    return await search_papers(query, limit, fallback_on_error=False)

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
    second_round_strategy: str = "coverage"
    enable_citation_expansion: bool = False
    max_citation_seeds: int = 1
    citation_results_per_seed: int = 5


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w+#.-]{2,}", (text or "").casefold())
        if token not in {
            "the", "and", "for", "with", "from", "using", "based", "paper",
            "papers", "research", "study", "about", "关于", "研究", "论文", "方法", "应用",
        }
    }


def _matches_constraint(text: str, value: str) -> bool:
    """Match an explicit constraint without losing simple inflections."""
    if value.casefold() == "transformer":
        return bool(re.search(r"\btransformers?\b", text, re.I))
    terms = _tokens(value)
    return bool(terms) and terms <= _tokens(text)


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


async def search_semantic_scholar(
    query: str,
    limit: int,
    *,
    raise_on_error: bool = False,
) -> list[dict]:
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
        if raise_on_error:
            raise
        return []


def rank_and_merge(
    ranked_lists: list[tuple[str, str, list[dict]]],
    plan: dict,
    limit: int,
) -> list[dict]:
    """Merge multi-route candidates and apply the validated calibrated base score.

    RRF, route agreement and authority remain attached as auditable evidence,
    but do not control final ordering because their independent gain did not
    replicate. The configured Cross Encoder performs the validated local
    semantic correction after this inexpensive candidate ordering.
    """
    candidates: dict[str, dict] = {}
    accumulators: dict[str, dict] = defaultdict(
        lambda: {
            "rrf": 0.0,
            "queries": set(),
            "sources": set(),
            "routes": set(),
            "primaryReciprocalRank": 0.0,
        }
    )
    planned_queries = plan.get("decomposed_queries") or [plan.get("research_question", "")]
    primary_query = str(planned_queries[0] if planned_queries else "").casefold()

    for source, query, papers in ranked_lists:
        for rank, incoming in enumerate(papers, start=1):
            key = _canonical_key(incoming)
            current = candidates.get(key)
            if current is None or len(incoming.get("abstract") or "") > len(current.get("abstract") or ""):
                candidates[key] = {**(current or {}), **incoming}
            accumulators[key]["rrf"] += 1.0 / (60 + rank)
            accumulators[key]["queries"].add(query)
            # Prefer the record's declared provenance. This prevents an offline
            # demo record returned by a retriever from being labelled OpenAlex.
            accumulators[key]["sources"].add(incoming.get("source") or source)
            accumulators[key]["routes"].add((source, query))
            if query.casefold() == primary_query:
                accumulators[key]["primaryReciprocalRank"] = max(
                    accumulators[key]["primaryReciprocalRank"],
                    1.0 / rank,
                )

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
        if constraints.get("open_source") is True and not paper.get("isOpenAccess"):
            continue

        title = str(paper.get("title") or "")
        abstract = str(paper.get("abstract") or "")
        searchable = f"{title} {abstract}"
        paper_terms = _tokens(searchable)
        methods = constraints.get("methods") or []
        if constraints.get("methods_required") and methods:
            if not any(_matches_constraint(searchable, method) for method in methods):
                continue
        topics = constraints.get("topics") or []
        if constraints.get("primary_topic_required") and topics:
            if not _matches_constraint(searchable, topics[0]):
                continue
        if any(excluded and excluded <= paper_terms for excluded in exclusions):
            continue

        matched_terms = sorted(query_terms & paper_terms)
        title_coverage = len(query_terms & _tokens(title)) / max(1, len(query_terms))
        abstract_coverage = len(query_terms & _tokens(abstract)) / max(1, len(query_terms))
        source_agreement = min(1.0, len(accumulators[key]["sources"]) / 2)
        query_coverage = min(
            1.0,
            len(accumulators[key]["queries"])
            / max(1, min(len(plan.get("decomposed_queries", [])), 3)),
        )
        authority = min(1.0, math.log1p(paper.get("citationCount") or 0) / math.log(10001))
        rrf = accumulators[key]["rrf"] / max_rrf
        route_agreement = min(1.0, len(accumulators[key]["routes"]) / 3)
        score = calibrated_base_score(
            accumulators[key]["primaryReciprocalRank"],
            title_coverage,
            abstract_coverage,
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
                "scoreEvidence": {
                    "primaryReciprocalRank": round(accumulators[key]["primaryReciprocalRank"], 6),
                    "titleCoverage": round(title_coverage, 6),
                    "abstractCoverage": round(abstract_coverage, 6),
                    "normalizedRrfEvidence": round(rrf, 6),
                    "routeAgreement": round(route_agreement, 6),
                    "queryCoverage": round(query_coverage, 6),
                    "sourceAgreement": round(source_agreement, 6),
                    "authority": round(authority, 6),
                },
                "relevanceScore": round(min(score, 1.0), 4),
                "relevanceLevel": "高度相关" if score >= 0.62 else "部分相关",
                "recommendReason": (
                    f"命中 {', '.join(evidence[:4]) or '核心检索语义'}；"
                    f"由 {len(matched_queries)} 个子查询、{len(sources)} 个数据源共同召回。"
                ),
                "metadataMissing": sorted(set(paper.get("metadataMissing") or []) | {
                    field for field, value in (("year", paper.get("year")),)
                    if value in (None, "")
                }),
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
    constraints = plan.get("constraints", {})
    topics = list(constraints.get("topics") or [])
    methods = list(constraints.get("methods") or [])
    datasets = list(constraints.get("datasets") or [])
    base_terms = _unique_text([*methods[:1], *topics[:1]])
    gap_queries: list[str] = []
    for gap in coverage.get("gaps", []):
        value = str(gap.get("value") or "").strip()
        dimension = str(gap.get("dimension") or "")
        if not value or dimension in {"year", "open_source"}:
            continue
        if dimension == "datasets":
            terms = [*base_terms, value]
        elif dimension == "venues":
            terms = [*base_terms, value]
        else:
            terms = [*methods[:1], value, *datasets[:1]]
        focused = " ".join(term for term in terms if term).strip()
        if focused:
            gap_queries.append(focused)
    planned_queries = plan.get("decomposed_queries", [])
    used = {" ".join(query.split()).casefold() for query in used_queries}
    return [
        query
        for query in _unique_text(gap_queries + planned_queries)
        if " ".join(query.split()).casefold() not in used
    ][:limit]


def generate_evolution_queries(
    plan: dict,
    papers: list[dict],
    used_queries: list[str],
    limit: int,
) -> list[str]:
    """Evolve queries from repeated new terms in the strongest current papers."""
    if limit <= 0 or not papers:
        return []
    original_terms = _tokens(
        " ".join([plan.get("research_question", ""), *used_queries])
    )
    counts: dict[str, int] = defaultdict(int)
    for paper in papers[:8]:
        for token in _tokens(f"{paper.get('title', '')} {paper.get('abstract', '')[:500]}"):
            if token not in original_terms and len(token) >= 4:
                counts[token] += 1
    expansion_terms = sorted(
        counts,
        key=lambda token: (-counts[token], -len(token), token),
    )
    research_question = plan.get("research_question", "")
    candidates = [
        f"{research_question} {term}"
        for term in expansion_terms
        if counts[term] >= 2
    ]
    used = {query.casefold() for query in used_queries}
    return [
        query for query in _unique_text(candidates)
        if query.casefold() not in used
    ][:limit]


def attach_query_evidence(plan: dict, papers: list[dict]) -> list[dict]:
    """Attach auditable abstract/full-text snippets for each explicit criterion."""
    constraints = plan.get("constraints", {})
    criteria = [
        (dimension, str(value))
        for dimension in ("topics", "methods", "datasets", "domains")
        for value in constraints.get(dimension, []) or []
        if str(value).strip()
    ]
    if not criteria:
        criteria = [("query", plan.get("research_question", ""))]

    enriched: list[dict] = []
    for paper in papers:
        full_text = str(paper.get("fullText") or paper.get("full_text") or "")
        source = "full_text" if full_text else "abstract"
        content = full_text or str(paper.get("abstract") or "")
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?。！？])\s+", content)
            if sentence.strip()
        ]
        if paper.get("title"):
            sentences.insert(0, str(paper["title"]).strip())

        evidence_items: list[dict] = []
        for dimension, value in criteria:
            expected = _tokens(value)
            if not expected or not sentences:
                continue
            ranked = sorted(
                (
                    (len(expected & _tokens(sentence)), -index, sentence)
                    for index, sentence in enumerate(sentences)
                ),
                reverse=True,
            )
            overlap, _, snippet = ranked[0]
            if overlap <= 0:
                continue
            matched = sorted(expected & _tokens(snippet))
            evidence_items.append(
                {
                    "criterion": dimension,
                    "value": value,
                    "source": source,
                    "snippet": snippet[:500],
                    "matchedTerms": matched,
                }
            )
        coverage = len(evidence_items) / max(1, len(criteria))
        enriched.append(
            {
                **paper,
                "evidence": [item["snippet"] for item in evidence_items],
                "criterionEvidence": evidence_items,
                "evidenceCoverage": round(coverage, 4),
            }
        )
    return enriched


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


async def _expand_citation_seeds(
    seeds: list[dict],
    expander: CitationExpander,
    results_per_seed: int,
    max_calls: int,
) -> dict:
    selected = [paper for paper in seeds if paper.get("id")][:max_calls]
    started = time.perf_counter()
    responses = await asyncio.gather(
        *(expander(str(paper["id"]), results_per_seed) for paper in selected),
        return_exceptions=True,
    )
    ranked_lists: list[tuple[str, str, list[dict]]] = []
    failures: list[str] = []
    for seed, response in zip(selected, responses):
        if isinstance(response, Exception):
            failures.append(f"CitationGraph: {type(response).__name__}")
            continue
        papers = response or []
        if papers:
            ranked_lists.append(
                ("CitationGraph", f"citation:{seed.get('title', seed['id'])}", papers)
            )
    return {
        "rankedLists": ranked_lists,
        "apiCalls": len(selected),
        "sourceCounts": {"CitationGraph": sum(len(item[2]) for item in ranked_lists)},
        "failures": failures,
        "seeds": [str(seed["id"]) for seed in selected],
        "durationMs": round((time.perf_counter() - started) * 1000),
    }


async def run_search_pipeline(
    query: str,
    limit: int = 20,
    breadth_level: int | None = None,
    budget: SearchBudget | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    retrievers: dict[str, PaperRetriever] | None = None,
    reranker: PaperReranker | None = None,
    reranker_metadata: dict | None = None,
    plan_override: dict | None = None,
    citation_expander: CitationExpander | None = None,
) -> dict:
    started = time.perf_counter()
    budget = budget or SearchBudget()
    retrievers = retrievers or {
        "OpenAlex": _search_openalex_strict,
        "Semantic Scholar": search_semantic_scholar,
    }
    citation_expander = citation_expander or get_related_papers

    planner_started = time.perf_counter()
    plan = (
        copy.deepcopy(plan_override)
        if isinstance(plan_override, dict)
        else await plan_search_query(query, llm_provider, llm_model)
    )
    if isinstance(plan_override, dict):
        plan["plannerMode"] = "replay"
        plan["cacheHit"] = False
        plan["coalesced"] = False
    planner_ms = round((time.perf_counter() - planner_started) * 1000)
    if isinstance(plan_override, dict):
        planner_ms = int(plan.get("experimentPlanningDurationMs") or planner_ms)
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

    citation_round = {
        "rankedLists": [],
        "apiCalls": 0,
        "sourceCounts": {},
        "failures": [],
        "seeds": [],
        "durationMs": 0,
    }
    citation_capacity = min(
        budget.max_citation_seeds,
        max(0, budget.max_api_calls - api_calls),
    )
    if budget.enable_citation_expansion and citation_capacity and first_candidates:
        citation_round = await _expand_citation_seeds(
            first_candidates,
            citation_expander,
            budget.citation_results_per_seed,
            citation_capacity,
        )
        ranked_lists.extend(citation_round["rankedLists"])
        api_calls += citation_round["apiCalls"]
        failures.extend(citation_round["failures"])
        for source, count in citation_round["sourceCounts"].items():
            source_counts[source] += count

    evolved_candidates = rank_and_merge(ranked_lists, plan, candidate_pool_size)
    evolved_coverage = analyze_coverage(plan, evolved_candidates)
    routing_query_terms = _tokens(
        " ".join(
            [plan.get("research_question", "")]
            + list((plan.get("constraints") or {}).get("topics") or [])
            + list((plan.get("constraints") or {}).get("methods") or [])
            + list((plan.get("constraints") or {}).get("datasets") or [])
        )
    )
    routing_decision = egrr_decision(
        routing_query_terms,
        [
            _tokens(f"{paper.get('title', '')} {paper.get('abstract', '')}")
            for paper in evolved_candidates[:20]
        ],
    )
    strategy = budget.second_round_strategy.casefold()
    if strategy not in {"none", "fixed", "coverage"}:
        raise ValueError("second_round_strategy must be none, fixed, or coverage")
    needs_second_round = routing_decision["route"]

    remaining_queries = max(0, budget.max_queries - len(first_queries))
    gap_queries: list[str] = []
    evolution_queries: list[str] = []
    if strategy == "none":
        second_queries = []
    elif strategy == "fixed":
        used = {item.casefold() for item in first_queries}
        second_queries = [
            item for item in all_queries if item.casefold() not in used
        ][:remaining_queries]
    else:
        gap_queries = generate_gap_queries(
            plan,
            evolved_coverage,
            first_queries,
            remaining_queries,
        ) if needs_second_round else []
        remaining_after_gaps = max(0, remaining_queries - len(gap_queries))
        evolution_queries = generate_evolution_queries(
            plan,
            evolved_candidates,
            first_queries + gap_queries,
            remaining_after_gaps,
        ) if needs_second_round else []
        second_queries = _unique_text(gap_queries + evolution_queries, remaining_queries)
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
    threshold = float(reranker_metadata.get("threshold") or 0.0)
    if reranker_metadata.get("status") == "completed" and threshold > 0 and candidates:
        selected = [
            paper
            for paper in candidates
            if float(paper.get("relevanceScore") or 0.0) >= threshold
        ]
        candidates = selected or candidates[:1]
        reranker_metadata.update(
            {
                "threshold": threshold,
                "selected": len(candidates),
                "selectorFallback": not bool(selected),
            }
        )
    adaptive_selector = reranker_metadata.get("adaptiveSelector") or {}
    breadth_selector = reranker_metadata.get("breadthSelector") or {}
    if breadth_selector.get("enabled") and candidates:
        selected_level = int(
            breadth_level
            if breadth_level is not None
            else breadth_selector.get("defaultLevel", 3)
        )
        candidates, breadth_decision = confidence_mass_select(
            candidates,
            breadth_level=selected_level,
        )
        reranker_metadata["breadthSelector"] = {
            **breadth_selector,
            **breadth_decision,
            "scoreSource": (
                "cross_encoder"
                if reranker_metadata.get("status") == "completed"
                else "multi_source_fusion"
            ),
        }
    elif (
        reranker_metadata.get("status") == "completed"
        and adaptive_selector.get("enabled")
        and candidates
    ):
        before_selection = len(candidates)
        candidates = confidence_aware_select(
            candidates,
            max_k=int(adaptive_selector.get("maxK", 2)),
            min_score=float(adaptive_selector.get("minScore", 0.60)),
            min_ratio=float(adaptive_selector.get("minRatio", 0.85)),
            max_drop=float(adaptive_selector.get("maxDrop", 0.10)),
        )
        adaptive_selector = {
            **adaptive_selector,
            "status": "completed",
            "candidatesBeforeSelection": before_selection,
            "selected": len(candidates),
        }
        reranker_metadata["adaptiveSelector"] = adaptive_selector
    papers = attach_query_evidence(plan, candidates[: max(1, min(limit, 50))])
    rerank_ms = round((time.perf_counter() - rerank_started) * 1000)
    total_ms = round((time.perf_counter() - started) * 1000)
    if isinstance(plan_override, dict):
        total_ms += planner_ms
    raw_candidates = sum(source_counts.values())

    if plan.get("fallbackReason"):
        planner_detail = f"大模型不可用，已由本地规则生成 {len(all_queries)} 个检索子查询"
    elif plan.get("plannerMode") == "cache":
        planner_detail = f"命中共享规划缓存，复用 {len(all_queries)} 个检索子查询"
    elif plan.get("plannerMode") == "replay":
        planner_detail = f"复用冻结查询规划，获得 {len(all_queries)} 个检索子查询"
    elif plan.get("plannerMode") == "heuristic":
        planner_detail = f"本地规则生成 {len(all_queries)} 个检索子查询，未调用大模型"
    elif plan.get("plannerMode") == "coalesced":
        planner_detail = f"合并并复用并发规划，获得 {len(all_queries)} 个检索子查询"
    else:
        planner_detail = f"大模型生成 {len(all_queries)} 个检索子查询"
    repaired_fields = (plan.get("constraintRepair") or {}).get("fields") or []
    if repaired_fields:
        planner_detail += f"；确定性校验补全 {', '.join(repaired_fields)}"

    trace = [
        {
            "stage": "查询规划",
            "status": "degraded" if plan.get("fallbackReason") else "completed",
            "detail": planner_detail,
            "durationMs": planner_ms,
        },
        {
            "stage": "首轮多源召回",
            "status": "completed" if first_round["rankedLists"] else "degraded",
            "detail": f"{len(first_queries)} 个查询，获得 {sum(first_round['sourceCounts'].values())} 条结果",
            "durationMs": first_round["durationMs"],
        },
        {
            "stage": "引文网络扩展",
            "status": "completed" if citation_round["apiCalls"] else "skipped",
            "detail": (
                f"从 {len(citation_round['seeds'])} 篇高相关种子扩展，获得 "
                f"{sum(citation_round['sourceCounts'].values())} 条候选"
                if citation_round["apiCalls"]
                else "未启用、没有有效种子或 API 预算不足"
            ),
            "durationMs": citation_round["durationMs"],
        },
        {
            "stage": "覆盖度诊断",
            "status": "completed",
            "detail": (
                f"首轮覆盖 {first_coverage['covered']}/{first_coverage['total']}；"
                f"引文扩展后覆盖 {evolved_coverage['covered']}/{evolved_coverage['total']}"
            ),
            "durationMs": 0,
        },
        {
            "stage": "缺口补检",
            "status": "completed" if second_round["apiCalls"] else "skipped",
            "detail": (
                f"新增 {len(second_queries)} 个查询，获得 "
                f"{sum(second_round['sourceCounts'].values())} 条结果；"
                f"其中 {len(evolution_queries)} 个由首轮结果演化"
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
            "detail": (
                f"去重后输出 {len(papers)} 篇论文，最终覆盖率 {final_coverage['score']:.0%}；"
                f"{(reranker_metadata.get('breadthSelector') or {}).get('breadthLabel', '默认')}范围"
            ),
            "durationMs": max(
                0,
                total_ms
                - planner_ms
                - first_round["durationMs"]
                - citation_round["durationMs"]
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
            "afterCitation": evolved_coverage,
            "final": final_coverage,
            "secondRoundTriggered": bool(second_round["apiCalls"]),
            "secondRoundQueries": second_queries if second_round["apiCalls"] else [],
            "evolutionQueries": evolution_queries if second_round["apiCalls"] else [],
            "routingDecision": routing_decision,
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
            "citationSeeds": citation_round["seeds"],
            "rawCandidates": raw_candidates,
            "returnedPapers": len(papers),
            "totalDurationMs": total_ms,
            "failures": failures,
            "reranker": reranker_metadata,
            "resultSelector": (
                reranker_metadata.get("breadthSelector")
                or reranker_metadata.get("adaptiveSelector")
                or {}
            ),
            "budget": {
                "maxQueries": budget.max_queries,
                "resultsPerSource": budget.results_per_source,
                "maxApiCalls": budget.max_api_calls,
                "secondRoundStrategy": strategy,
                "citationExpansion": budget.enable_citation_expansion,
                "maxCitationSeeds": budget.max_citation_seeds,
                "citationResultsPerSeed": budget.citation_results_per_seed,
            },
        },
    }
