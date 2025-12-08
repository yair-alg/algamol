"""SQLAlchemy ORM models for Algamol."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float,
    ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Paper(Base):
    """Represents a scientific paper with metadata."""

    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core metadata
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    year = Column(Integer, nullable=True, index=True)
    journal_or_venue = Column(String(500), nullable=True)

    # Authors (stored as JSON array)
    authors = Column(JSON, nullable=True)

    # Identifiers
    doi = Column(String(255), nullable=True, index=True, unique=True)
    main_external_id_type = Column(String(50), nullable=True)  # e.g., "pmid", "arxiv", "openalex"
    main_external_id_value = Column(String(255), nullable=True)
    external_ids = Column(JSON, nullable=True)  # All IDs as dict

    # Source information
    source_name = Column(String(100), nullable=False, index=True)
    source_tier = Column(Integer, nullable=False, index=True)
    source_url = Column(Text, nullable=True)

    # Open access and retrieval status
    open_access_flag = Column(Boolean, default=False, index=True)
    retrieval_status = Column(String(50), nullable=False, default="pending")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    files = relationship("File", back_populates="paper", cascade="all, delete-orphan")
    query_results = relationship("QueryResult", back_populates="paper", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_paper_search", "title", "year", "source_name"),
        Index("idx_paper_external_id", "main_external_id_type", "main_external_id_value"),
    )

    def __repr__(self):
        return f"<Paper(id={self.id}, doi={self.doi}, title={self.title[:50]}...)>"


class File(Base):
    """Represents a downloaded file (typically PDF) associated with a paper."""

    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)

    # File information
    local_path = Column(String(1000), nullable=False)
    checksum = Column(String(64), nullable=False, index=True)  # SHA-256
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False, default="application/pdf")

    # Download information
    download_url = Column(Text, nullable=True)
    download_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    download_status = Column(String(50), nullable=False, default="success")

    # Relationships
    paper = relationship("Paper", back_populates="files")

    def __repr__(self):
        return f"<File(id={self.id}, paper_id={self.paper_id}, path={self.local_path})>"


class Query(Base):
    """Represents a search query executed by the user."""

    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Query information
    query_type = Column(String(50), nullable=False, index=True)  # "topic-search", "id-list", "corpus-search"
    raw_query_text = Column(Text, nullable=False)
    filters_json = Column(JSON, nullable=True)

    # Execution information
    sources_used = Column(JSON, nullable=True)  # List of source names
    execution_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    execution_status = Column(String(50), nullable=False, default="pending")

    # Results summary
    total_results = Column(Integer, default=0)
    new_papers = Column(Integer, default=0)
    existing_papers = Column(Integer, default=0)
    pdfs_downloaded = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    error_log = Column(JSON, nullable=True)

    # Relationships
    query_results = relationship("QueryResult", back_populates="query", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Query(id={self.id}, type={self.query_type}, text={self.raw_query_text[:50]}...)>"


class QueryResult(Base):
    """Junction table linking queries to papers with ranking."""

    __tablename__ = "query_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(Integer, ForeignKey("queries.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)

    # Result metadata
    rank = Column(Integer, nullable=True)
    source_name = Column(String(100), nullable=False)
    relevance_score = Column(Float, nullable=True)

    # Relationships
    query = relationship("Query", back_populates="query_results")
    paper = relationship("Paper", back_populates="query_results")

    __table_args__ = (
        Index("idx_query_results", "query_id", "paper_id", unique=True),
    )

    def __repr__(self):
        return f"<QueryResult(query_id={self.query_id}, paper_id={self.paper_id}, rank={self.rank})>"
