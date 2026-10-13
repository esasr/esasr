from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional


# ── Auth Schemas ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

    @field_validator('username')
    @classmethod
    def username_min_length(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError('Username must be at least 2 characters')
        return v

    @field_validator('password')
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: 'UserProfile'


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Paper Schemas ─────────────────────────────────────────────────────────────

class SavePaperRequest(BaseModel):
    paper_id: str
    paper_title: str
    paper_data: Optional[str] = None  # JSON string


class SavedPaperResponse(BaseModel):
    id: int
    paper_id: str
    paper_title: str
    paper_data: Optional[str]
    saved_at: datetime

    model_config = {"from_attributes": True}


# ── Search History Schemas ─────────────────────────────────────────────────────

class SearchHistoryCreate(BaseModel):
    query: str


class SearchHistoryResponse(BaseModel):
    id: int
    query: str
    searched_at: datetime

    model_config = {"from_attributes": True}


class BrowsingHistoryCreate(BaseModel):
    paper_id: str
    paper_title: str


class BrowsingHistoryResponse(BrowsingHistoryCreate):
    id: int
    viewed_at: datetime
    model_config = {"from_attributes": True}


class CollectionCreate(BaseModel):
    name: str


class CollectionPaperCreate(BaseModel):
    paper_id: str
    paper_title: str


class CollectionPaperResponse(CollectionPaperCreate):
    id: int
    added_at: datetime
    model_config = {"from_attributes": True}


class CollectionResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    papers: list[CollectionPaperResponse] = []
    model_config = {"from_attributes": True}
