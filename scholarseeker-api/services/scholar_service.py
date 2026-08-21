import asyncio
import httpx
from config import cfg
from redis_db import cache_get, cache_set
from neo4j_db import run_query
import hashlib
from services.semantic_scholar_client import get_json as semantic_scholar_get_json

_oa = cfg.openalex
_s2 = cfg.semantic_scholar

_OFFLINE_PAPERS = [
    {"id": "local_llava_med", "title": "LLaVA-Med: Training a Large Language-and-Vision Assistant for Biomedicine", "authors": "Ji Woong Kim, T. Y. Liu, et al.", "venue": "NeurIPS", "year": 2023, "citationCount": 204, "abstract": "We present a large language-and-vision assistant adapted for biomedical image understanding and conversational clinical reasoning.", "concepts": ["Multimodal Learning", "Medical Imaging", "Large Language Models"]},
    {"id": "local_biomedclip", "title": "BiomedCLIP: A Multimodal Biomedical Foundation Model Pretrained from Fifteen Million Scientific Image-Text Pairs", "authors": "S. Zhang, A. A. Wong, et al.", "venue": "arXiv", "year": 2023, "citationCount": 318, "abstract": "A biomedical vision-language foundation model trained on large-scale scientific image-text pairs for robust cross-modal retrieval and classification.", "concepts": ["Foundation Models", "Biomedical AI", "Vision-Language Models"]},
    {"id": "local_medpalm", "title": "Towards Expert-Level Medical Question Answering with Large Language Models", "authors": "Karan Singhal, Shekoofeh Azizi, et al.", "venue": "Nature", "year": 2025, "citationCount": 1560, "abstract": "This work evaluates large language models for medical question answering and explores methods for safer, more useful clinical assistance.", "concepts": ["Medical AI", "Question Answering", "Large Language Models"]},
    {"id": "local_rag", "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", "authors": "Patrick Lewis, Ethan Perez, et al.", "venue": "NeurIPS", "year": 2020, "citationCount": 8400, "abstract": "Retrieval-augmented generation combines parametric and non-parametric memory to improve factual generation on knowledge-intensive tasks.", "concepts": ["Information Retrieval", "Natural Language Processing", "Generative AI"]},
]


def _offline_detail(paper_id: str) -> dict:
    paper = next((item for item in _OFFLINE_PAPERS if item["id"] == paper_id), _OFFLINE_PAPERS[0])
    return {
        **paper,
        "authorDetails": [{"name": name.strip(), "institution": ""} for name in paper["authors"].replace(" et al.", "").split(",")],
        "publicationDate": f"{paper['year']}-01-01", "type": "article", "referencedWorksCount": 28,
        "relatedWorksCount": len(_OFFLINE_PAPERS) - 1, "doi": "", "url": "", "pdfUrl": "", "isOpenAccess": True,
        "offline": True,
    }

# ── Helpers ────────────────────────────────────────────────────────
def _cache_key(prefix: str, identifier: str) -> str:
    hashed = hashlib.md5(identifier.encode()).hexdigest()
    return f"{prefix}:{hashed}"

def _build_headers():
    headers = {}
    if _oa.get("email"):
        headers["User-Agent"] = f"mailto:{_oa.get('email')}"
    return headers


def _openalex_params(**params):
    """Attach the optional OpenAlex API key to every API request."""
    if api_key := _oa.get("api_key"):
        params["api_key"] = api_key
    return params

def _reconstruct_abstract(inverted_index: dict) -> str:
    if not inverted_index:
        return "No abstract available."
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    words.sort(key=lambda x: x[0])
    return " ".join([w[1] for w in words])


def _authors(item: dict, limit: int = 5) -> tuple[str, list[dict]]:
    """Return a display string and structured author metadata from OpenAlex."""
    authorships = item.get("authorships", [])
    author_details = [
        {
            "name": entry.get("author", {}).get("display_name", "Unknown author"),
            "institution": next(
                (inst.get("display_name") for inst in entry.get("institutions", []) if inst.get("display_name")),
                "",
            ),
        }
        for entry in authorships
    ]
    names = [author["name"] for author in author_details[:limit]]
    display = ", ".join(names)
    if len(author_details) > limit:
        display += " et al."
    return display, author_details


def _venue(item: dict) -> str:
    source = (item.get("primary_location") or {}).get("source") or {}
    return source.get("display_name") or "Preprint"


def _paper_summary(item: dict) -> dict:
    """Normalize an OpenAlex work for search and recommendation cards."""
    paper_id = (item.get("id") or "").split("/")[-1]
    authors, _ = _authors(item, limit=3)
    return {
        "id": paper_id,
        "sourceId": paper_id,
        "title": item.get("title") or "Untitled",
        "authors": authors,
        "venue": _venue(item),
        "year": item.get("publication_year"),
        "abstract": _reconstruct_abstract(item.get("abstract_inverted_index")),
        "citationCount": item.get("cited_by_count") or 0,
        "isOpenAccess": bool((item.get("open_access") or {}).get("is_oa")),
        "doi": (item.get("doi") or "").replace("https://doi.org/", ""),
        "url": item.get("id") or "",
        "source": "OpenAlex",
        "relevanceScore": item.get("relevance_score") or 0,
        "recommendReason": "Related through OpenAlex's citation and semantic-work graph.",
    }


def _s2_summary(item: dict) -> dict:
    external_ids = item.get("externalIds") or {}
    pdf = item.get("openAccessPdf") or {}
    return {
        "id": f"s2_{item.get('paperId')}",
        "sourceId": item.get("paperId"),
        "title": item.get("title") or "Untitled",
        "authors": ", ".join(author.get("name", "") for author in item.get("authors") or [])
        or "Unknown authors",
        "authorDetails": [
            {"name": author.get("name", "Unknown author"), "institution": ""}
            for author in item.get("authors") or []
        ],
        "venue": item.get("venue") or "Preprint",
        "year": item.get("year"),
        "publicationDate": str(item.get("year") or ""),
        "type": "article",
        "abstract": item.get("abstract") or "No abstract available.",
        "citationCount": item.get("citationCount") or 0,
        "referencedWorksCount": item.get("referenceCount") or 0,
        "relatedWorksCount": item.get("citationCount") or 0,
        "doi": external_ids.get("DOI") or "",
        "url": item.get("url") or "",
        "pdfUrl": pdf.get("url") or "",
        "isOpenAccess": bool(pdf.get("url")),
        "concepts": [
            field.get("category") if isinstance(field, dict) else str(field)
            for field in item.get("fieldsOfStudy") or []
            if (field.get("category") if isinstance(field, dict) else field)
        ],
        "source": "Semantic Scholar",
    }


async def _get_s2_paper(paper_id: str) -> dict:
    fields = (
        "paperId,title,authors,venue,year,abstract,citationCount,referenceCount,"
        "openAccessPdf,externalIds,url,fieldsOfStudy"
    )
    data = await semantic_scholar_get_json(
        f"/paper/{paper_id}",
        {"fields": fields},
    )
    return _s2_summary(data)


async def _get_s2_related(paper_id: str, limit: int) -> list[dict]:
    fields = "paperId,title,authors,venue,year,abstract,citationCount,openAccessPdf,externalIds,url"
    data = await semantic_scholar_get_json(
        f"/paper/{paper_id}/citations",
        {"limit": limit, "fields": fields},
    )
    return [
        _s2_summary(item["citingPaper"])
        for item in data.get("data", [])
        if item.get("citingPaper")
    ]


# ── API ────────────────────────────────────────────────────────────
async def search_papers(query: str, limit: int = None):
    limit = limit or _oa.get("per_page", 10)
    
    cache_key = _cache_key("search", f"{query}:{limit}")
    cached = await cache_get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=_oa.timeout, headers=_build_headers()) as client:
        url = f"{_oa.base_url}{_oa.works_endpoint}"
        params = {
            "search": query,
            "per-page": limit,
            "sort": "relevance_score:desc"
        }
        try:
            response = await client.get(url, params=_openalex_params(**params))
            if response.status_code == 429:
                retry_after = min(float(response.headers.get("Retry-After", "1")), 2.0)
                await asyncio.sleep(retry_after)
                response = await client.get(url, params=_openalex_params(**params))
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", []):
                summary = _paper_summary(item)
                summary["year"] = summary["year"] or 2024
                summary["relevanceScore"] = summary["relevanceScore"] or 0.9
                summary["recommendReason"] = "Matched from OpenAlex."
                results.append(summary)
            
            if results:
                await cache_set(cache_key, results, ttl=cfg.redis.ttl.get("search_results", 300))
            return results

        except Exception as e:
            print(f"[OpenAlex Error] search_papers: {e}")
            return get_mock_papers(query)


def get_mock_papers(query: str):
    query_terms = {
        token
        for token in query.casefold().replace("-", " ").split()
        if len(token) >= 3
    }
    results = []
    for index, paper in enumerate(_OFFLINE_PAPERS):
        searchable = (
            f"{paper['title']} {paper['abstract']} {' '.join(paper.get('concepts', []))}"
        ).casefold()
        required_matches = min(2, len(query_terms))
        if query_terms and sum(term in searchable for term in query_terms) < required_matches:
            continue
        results.append({
            **paper, "isOpenAccess": True, "relevanceScore": round(0.98 - index * 0.06, 2),
            "recommendReason": "本地离线演示数据：外部学术数据源暂不可用。",
        })
    return results


async def get_paper_details(paper_id: str):
    if paper_id.startswith(("mock_", "local_")):
        return _offline_detail(paper_id)

    cache_key = f"paper_detail:{paper_id}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    if paper_id.startswith("s2_"):
        try:
            details = await _get_s2_paper(paper_id.removeprefix("s2_"))
            await cache_set(
                cache_key,
                details,
                ttl=cfg.redis.ttl.get("paper_detail", 3600),
            )
            return details
        except Exception as e:
            print(f"[Semantic Scholar Error] get_paper_details: {e}")
            return {
                "id": paper_id,
                "title": "论文详情暂不可用",
                "authors": "",
                "venue": "Semantic Scholar",
                "abstract": "Semantic Scholar 当前请求繁忙，请稍后刷新。",
                "temporaryError": True,
            }

    async with httpx.AsyncClient(timeout=_oa.timeout, headers=_build_headers()) as client:
        url = f"{_oa.base_url}{_oa.works_endpoint}/{paper_id}"
        try:
            response = await client.get(url, params=_openalex_params())
            response.raise_for_status()
            item = response.json()

            authors, author_details = _authors(item)

            pdf_url = ""
            if item.get("open_access", {}).get("is_oa") and item.get("open_access", {}).get("oa_url"):
                pdf_url = item["open_access"]["oa_url"]

            details = {
                "id": paper_id,
                "title": item.get("title") or "Untitled",
                "authors": authors,
                "authorDetails": author_details,
                "venue": _venue(item),
                "year": item.get("publication_year"),
                "publicationDate": item.get("publication_date"),
                "type": item.get("type"),
                "abstract": _reconstruct_abstract(item.get("abstract_inverted_index")),
                "citationCount": item.get("cited_by_count") or 0,
                "referencedWorksCount": item.get("referenced_works_count") or 0,
                "relatedWorksCount": len(item.get("related_works") or []),
                "doi": item.get("doi", "").replace("https://doi.org/", ""),
                "url": item.get("id", ""),
                "pdfUrl": pdf_url,
                "isOpenAccess": bool(item.get("open_access", {}).get("is_oa")),
                "concepts": [concept.get("display_name") for concept in item.get("concepts", [])[:6]],
            }

            await cache_set(cache_key, details, ttl=cfg.redis.ttl.get("paper_detail", 3600))
            return details

        except Exception as e:
            print(f"[OpenAlex Error] get_paper_details: {e}")
            return {"id": paper_id, "title": "[Mock] API Error"}


async def get_related_papers(paper_id: str, limit: int = 5):
    """Fetch dynamic recommendations from OpenAlex's related-work graph."""
    if paper_id.startswith(("mock_", "local_")):
        return [
            {**item, "isOpenAccess": True, "relevanceScore": 0.9, "recommendReason": "本地关联文献推荐。"}
            for item in _OFFLINE_PAPERS if item["id"] != paper_id
        ][:limit]

    cache_key = f"paper_related:{paper_id}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    if paper_id.startswith("s2_"):
        try:
            related = await _get_s2_related(paper_id.removeprefix("s2_"), limit)
            await cache_set(
                cache_key,
                related,
                ttl=cfg.redis.ttl.get("paper_detail", 3600),
            )
            return related
        except Exception as e:
            print(f"[Semantic Scholar Error] get_related_papers: {e}")
            return []

    async with httpx.AsyncClient(timeout=_oa.timeout, headers=_build_headers()) as client:
        try:
            source = await client.get(f"{_oa.base_url}{_oa.works_endpoint}/{paper_id}", params=_openalex_params())
            source.raise_for_status()
            related_ids = [work_id.split("/")[-1] for work_id in source.json().get("related_works", [])[:limit]]

            responses = await asyncio.gather(
                *[client.get(f"{_oa.base_url}{_oa.works_endpoint}/{related_id}", params=_openalex_params()) for related_id in related_ids],
                return_exceptions=True,
            )
            related = []
            for response in responses:
                if isinstance(response, Exception) or response.status_code != 200:
                    continue
                summary = _paper_summary(response.json())
                summary["recommendReason"] = "OpenAlex related-work graph recommendation."
                related.append(summary)

            await cache_set(cache_key, related, ttl=cfg.redis.ttl.get("paper_detail", 3600))
            return related
        except Exception as e:
            print(f"[OpenAlex Error] get_related_papers: {e}")
            return []


async def get_citation_graph(paper_id: str):
    """
    获取论文引用关系图。OpenAlex 包含 referenced_works 和 related_works。
    由于拉取引用树较为耗时，我们用 related_works + referenced_works 模拟并存入 Neo4j。
    """
    if paper_id.startswith(("mock_", "local_")):
        center = _offline_detail(paper_id)
        related = [item for item in _OFFLINE_PAPERS if item["id"] != paper_id][:4]
        return {
            "nodes": [{"id": paper_id, "style": {"labelText": center["title"][:36], "fill": "#409eff", "r": 35}}] + [
                {"id": item["id"], "style": {"labelText": item["title"][:28], "fill": "#67c23a"}} for item in related
            ],
            "edges": [{"source": item["id"], "target": paper_id} for item in related],
        }
    if paper_id.startswith("s2_"):
        center = await get_paper_details(paper_id)
        related = await get_related_papers(paper_id, 6)
        return {
            "nodes": [
                {
                    "id": paper_id,
                    "style": {
                        "labelText": (center.get("title") or "Current Paper")[:50],
                        "fill": "#409eff",
                        "r": 35,
                    },
                }
            ]
            + [
                {
                    "id": item["id"],
                    "style": {
                        "labelText": item["title"][:40],
                        "fill": "#67c23a",
                    },
                }
                for item in related
            ],
            "edges": [{"source": item["id"], "target": paper_id} for item in related],
        }

    # 1. 尝试从图数据库直接返回（为了演示完整结构，这里每次依然拉取OpenAlex，真实生产环境应直接读Neo4j并返回网络图）
    
    async with httpx.AsyncClient(timeout=_oa.timeout, headers=_build_headers()) as client:
        url = f"{_oa.base_url}{_oa.works_endpoint}/{paper_id}"
        try:
            response = await client.get(url, params=_openalex_params())
            response.raise_for_status()
            data = response.json()

            nodes, edges = [], []
            center_title = (data.get("title") or "Current Paper")[:50]
            nodes.append({
                "id": paper_id,
                "style": {"labelText": center_title, "fill": "#409eff", "r": 35},
            })

            # 中心节点存入 Neo4j
            await run_query(
                "MERGE (p:Paper {paperId: $id}) SET p.title = $title", 
                {"id": paper_id, "title": center_title}
            )

            # 参考文献 (References)
            refs = data.get("referenced_works", [])[:5]
            for i, ref_url in enumerate(refs):
                rid = ref_url.split("/")[-1]
                rtitle = f"Reference {i+1}"
                nodes.append({"id": rid, "style": {"labelText": rtitle, "fill": "#e6a23c"}})
                edges.append({"source": paper_id, "target": rid})
                
                await run_query(
                    "MERGE (r:Paper {paperId: $rid}) SET r.title = $title "
                    "WITH r MERGE (p:Paper {paperId: $pid}) "
                    "MERGE (p)-[:CITES]->(r)",
                    {"rid": rid, "title": rtitle, "pid": paper_id}
                )

            # 相关文献 (Related works) - 用作被引用的模拟
            related = data.get("related_works", [])[:5]
            for i, rel_url in enumerate(related):
                cid = rel_url.split("/")[-1]
                ctitle = f"Related {i+1}"
                nodes.append({"id": cid, "style": {"labelText": ctitle, "fill": "#67c23a"}})
                edges.append({"source": cid, "target": paper_id})
                
                await run_query(
                    "MERGE (c:Paper {paperId: $cid}) SET c.title = $title "
                    "WITH c MERGE (p:Paper {paperId: $pid}) "
                    "MERGE (c)-[:CITES]->(p)",
                    {"cid": cid, "title": ctitle, "pid": paper_id}
                )

            return {"nodes": nodes, "edges": edges}

        except Exception as e:
            print(f"[OpenAlex Error] get_citation_graph: {e}")
            return {"nodes": [{"id": paper_id, "style": {"labelText": "API Error", "fill": "#f56c6c", "r": 35}}], "edges": []}
