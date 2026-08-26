from fastapi import APIRouter, HTTPException
from typing import Optional
from services.scholar_service import search_papers, get_paper_details, get_citation_graph, get_related_papers

router = APIRouter()

@router.get("/search")
async def search(query: str, limit: int = 10):
    try:
        results = await search_papers(query, limit)
        return {"data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{paper_id}")
async def paper_details(paper_id: str):
    try:
        details = await get_paper_details(paper_id)
        return {"data": details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{paper_id}/graph")
async def citation_graph(paper_id: str):
    try:
        graph = await get_citation_graph(paper_id)
        return {"data": graph}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}/related")
async def related_papers(paper_id: str, limit: int = 5):
    try:
        return {"data": await get_related_papers(paper_id, min(max(limit, 1), 10))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
