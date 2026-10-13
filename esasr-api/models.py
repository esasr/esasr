from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    saved_papers = relationship("SavedPaper", back_populates="user", cascade="all, delete-orphan")
    search_history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    browsing_history = relationship("BrowsingHistory", back_populates="user", cascade="all, delete-orphan")
    collections = relationship("ResearchCollection", back_populates="user", cascade="all, delete-orphan")


class SavedPaper(Base):
    __tablename__ = "saved_papers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    paper_id = Column(String(100), nullable=False, index=True)
    paper_title = Column(String(500))
    paper_data = Column(Text)
    saved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="saved_papers")


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    query = Column(String(500), nullable=False)
    searched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="search_history")


class BrowsingHistory(Base):
    __tablename__ = "browsing_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    paper_id = Column(String(100), nullable=False, index=True)
    paper_title = Column(String(500), nullable=False)
    viewed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="browsing_history")


class ResearchCollection(Base):
    __tablename__ = "research_collections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="collections")
    papers = relationship("CollectionPaper", back_populates="collection", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_collection_user_name"),)


class CollectionPaper(Base):
    __tablename__ = "collection_papers"

    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(Integer, ForeignKey("research_collections.id"), nullable=False)
    paper_id = Column(String(100), nullable=False, index=True)
    paper_title = Column(String(500), nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    collection = relationship("ResearchCollection", back_populates="papers")
    __table_args__ = (UniqueConstraint("collection_id", "paper_id", name="uq_collection_paper"),)
