from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from typing import List
from database import get_db
import models
import schemas
from auth import get_current_user
from services.scholar_service import search_papers

router = APIRouter()


# ── Saved Papers ──────────────────────────────────────────────────────────────

@router.get("/saved-papers", response_model=List[schemas.SavedPaperResponse])
async def get_saved_papers(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.SavedPaper)
        .where(models.SavedPaper.user_id == current_user.id)
        .order_by(models.SavedPaper.saved_at.desc())
    )
    return result.scalars().all()


@router.post("/saved-papers", response_model=schemas.SavedPaperResponse, status_code=201)
async def save_paper(
    data: schemas.SavePaperRequest,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Avoid duplicates
    result = await db.execute(
        select(models.SavedPaper).where(
            models.SavedPaper.user_id == current_user.id,
            models.SavedPaper.paper_id == data.paper_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    saved = models.SavedPaper(
        user_id=current_user.id,
        paper_id=data.paper_id,
        paper_title=data.paper_title,
        paper_data=data.paper_data,
    )
    db.add(saved)
    await db.flush()
    await db.refresh(saved)
    return saved


@router.delete("/saved-papers/{paper_id}", status_code=204)
async def remove_saved_paper(
    paper_id: str,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.SavedPaper).where(
            models.SavedPaper.user_id == current_user.id,
            models.SavedPaper.paper_id == paper_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Saved paper not found")
    await db.delete(record)


@router.get("/saved-papers/ids")
async def get_saved_paper_ids(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.SavedPaper.paper_id)
        .where(models.SavedPaper.user_id == current_user.id)
    )
    return {"ids": [row[0] for row in result.all()]}


# ── Search History ────────────────────────────────────────────────────────────

@router.get("/search-history", response_model=List[schemas.SearchHistoryResponse])
async def get_search_history(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.SearchHistory)
        .where(models.SearchHistory.user_id == current_user.id)
        .order_by(models.SearchHistory.searched_at.desc())
        .limit(20)
    )
    return result.scalars().all()


@router.post("/search-history", response_model=schemas.SearchHistoryResponse, status_code=201)
async def add_search_history(
    data: schemas.SearchHistoryCreate,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = models.SearchHistory(
        user_id=current_user.id,
        query=data.query,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


@router.get("/browsing-history", response_model=List[schemas.BrowsingHistoryResponse])
async def get_browsing_history(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.BrowsingHistory).where(models.BrowsingHistory.user_id == current_user.id).order_by(models.BrowsingHistory.viewed_at.desc()).limit(20))
    return result.scalars().all()


@router.post("/browsing-history", response_model=schemas.BrowsingHistoryResponse, status_code=201)
async def add_browsing_history(data: schemas.BrowsingHistoryCreate, current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(models.BrowsingHistory).where(models.BrowsingHistory.user_id == current_user.id, models.BrowsingHistory.paper_id == data.paper_id))
    record = existing.scalar_one_or_none()
    if record:
        record.paper_title = data.paper_title
        record.viewed_at = datetime.now(timezone.utc)
        await db.flush(); await db.refresh(record)
        return record
    record = models.BrowsingHistory(user_id=current_user.id, **data.model_dump())
    db.add(record); await db.flush(); await db.refresh(record)
    return record


@router.get("/collections", response_model=List[schemas.CollectionResponse])
async def get_collections(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.ResearchCollection).options(selectinload(models.ResearchCollection.papers)).where(models.ResearchCollection.user_id == current_user.id).order_by(models.ResearchCollection.created_at.desc()))
    return result.scalars().unique().all()


@router.post("/collections", response_model=schemas.CollectionResponse, status_code=201)
async def create_collection(data: schemas.CollectionCreate, current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Collection name cannot be empty")
    existing = await db.execute(select(models.ResearchCollection).where(models.ResearchCollection.user_id == current_user.id, models.ResearchCollection.name == name))
    record = existing.scalar_one_or_none()
    if record:
        await db.refresh(record, ["papers"])
        return record
    record = models.ResearchCollection(user_id=current_user.id, name=name)
    db.add(record); await db.flush(); await db.refresh(record, ["papers"])
    return record


@router.post("/collections/{collection_id}/papers", response_model=schemas.CollectionPaperResponse, status_code=201)
async def add_collection_paper(collection_id: int, data: schemas.CollectionPaperCreate, current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    collection = await db.scalar(select(models.ResearchCollection).where(models.ResearchCollection.id == collection_id, models.ResearchCollection.user_id == current_user.id))
    if not collection: raise HTTPException(status_code=404, detail="Collection not found")
    existing = await db.scalar(select(models.CollectionPaper).where(models.CollectionPaper.collection_id == collection_id, models.CollectionPaper.paper_id == data.paper_id))
    if existing: return existing
    record = models.CollectionPaper(collection_id=collection_id, **data.model_dump())
    db.add(record); await db.flush(); await db.refresh(record)
    return record


@router.get("/recommendations")
async def recommendations(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    history = await db.execute(select(models.SearchHistory.query).where(models.SearchHistory.user_id == current_user.id).order_by(models.SearchHistory.searched_at.desc()).limit(3))
    queries = [row[0] for row in history.all()]
    if not queries: return {"data": []}
    papers = await search_papers(" ".join(queries), limit=6)
    saved = await db.execute(select(models.SavedPaper.paper_id).where(models.SavedPaper.user_id == current_user.id))
    saved_ids = {row[0] for row in saved.all()}
    return {"data": [paper for paper in papers if paper["id"] not in saved_ids][:5]}


@router.get("/recommended-queries")
async def recommended_queries(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Turn a user's recent research intent into immediately reusable query directions."""
    result = await db.execute(
        select(models.SearchHistory.query)
        .where(models.SearchHistory.user_id == current_user.id)
        .order_by(models.SearchHistory.searched_at.desc())
        .limit(2)
    )
    queries = [row[0].strip() for row in result.all() if row[0].strip()]
    suggestions = []
    for query in queries:
        suggestions.extend([
            f"{query}，关注近三年高被引论文与开源实现",
            f"{query}，比较主流方法、基准数据集与评测指标",
        ])
    return {"data": suggestions[:4]}
