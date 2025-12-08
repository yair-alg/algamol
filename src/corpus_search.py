"""Local corpus search and filtering."""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import or_, and_, text
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Paper, File

logger = logging.getLogger(__name__)


class CorpusSearch:
    """Search and filter local paper corpus."""

    def __init__(self):
        """Initialize corpus search."""
        self.db = get_db()

    def search(
        self,
        query_text: Optional[str] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        source_tier: Optional[int] = None,
        has_pdf: Optional[bool] = None,
        source_name: Optional[str] = None,
        author: Optional[str] = None,
        journal: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Search local corpus with filters.

        Args:
            query_text: Text search in title and abstract
            year_start: Minimum publication year
            year_end: Maximum publication year
            source_tier: Filter by source tier (1, 2, or 3)
            has_pdf: Filter papers with/without PDFs
            source_name: Filter by source name
            author: Search for author name
            journal: Search in journal name
            limit: Maximum results
            offset: Result offset for pagination

        Returns:
            List of paper dictionaries with metadata
        """
        with self.db.get_session() as session:
            query = session.query(Paper)

            # Text search using FTS if available
            if query_text:
                try:
                    # Try FTS5 full-text search
                    fts_results = session.execute(
                        text("SELECT paper_id FROM papers_fts WHERE papers_fts MATCH :query LIMIT :limit"),
                        {"query": query_text, "limit": limit * 2}
                    ).fetchall()

                    paper_ids = [r[0] for r in fts_results]
                    if paper_ids:
                        query = query.filter(Paper.id.in_(paper_ids))
                    else:
                        # Fallback to LIKE search
                        query = query.filter(
                            or_(
                                Paper.title.ilike(f"%{query_text}%"),
                                Paper.abstract.ilike(f"%{query_text}%")
                            )
                        )
                except Exception as e:
                    logger.debug(f"FTS search failed, using LIKE: {e}")
                    # Fallback to LIKE search
                    query = query.filter(
                        or_(
                            Paper.title.ilike(f"%{query_text}%"),
                            Paper.abstract.ilike(f"%{query_text}%")
                        )
                    )

            # Year filters
            if year_start:
                query = query.filter(Paper.year >= year_start)
            if year_end:
                query = query.filter(Paper.year <= year_end)

            # Source filters
            if source_tier:
                query = query.filter(Paper.source_tier == source_tier)
            if source_name:
                query = query.filter(Paper.source_name == source_name)

            # PDF filter
            if has_pdf is not None:
                if has_pdf:
                    query = query.join(File).filter(File.paper_id == Paper.id)
                else:
                    query = query.outerjoin(File).filter(File.id.is_(None))

            # Author filter
            if author:
                # Search in JSON authors array
                query = query.filter(
                    text(f"json_extract(authors, '$') LIKE '%{author}%'")
                )

            # Journal filter
            if journal:
                query = query.filter(Paper.journal_or_venue.ilike(f"%{journal}%"))

            # Apply pagination
            query = query.order_by(Paper.created_at.desc())
            query = query.limit(limit).offset(offset)

            # Execute query
            papers = query.all()

            # Convert to dictionaries
            results = []
            for paper in papers:
                paper_dict = {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "journal_or_venue": paper.journal_or_venue,
                    "abstract": paper.abstract,
                    "doi": paper.doi,
                    "main_external_id_type": paper.main_external_id_type,
                    "main_external_id_value": paper.main_external_id_value,
                    "source_name": paper.source_name,
                    "source_tier": paper.source_tier,
                    "source_url": paper.source_url,
                    "open_access_flag": paper.open_access_flag,
                    "retrieval_status": paper.retrieval_status,
                    "created_at": paper.created_at.isoformat(),
                    "files": []
                }

                # Add file information
                for file in paper.files:
                    paper_dict["files"].append({
                        "id": file.id,
                        "local_path": file.local_path,
                        "checksum": file.checksum,
                        "file_size_bytes": file.file_size_bytes,
                        "mime_type": file.mime_type,
                        "download_url": file.download_url,
                        "download_status": file.download_status
                    })

                results.append(paper_dict)

            return results

    def get_paper_by_id(self, paper_id: int) -> Optional[Dict[str, Any]]:
        """Get a single paper by ID.

        Args:
            paper_id: Paper database ID

        Returns:
            Paper dictionary or None
        """
        results = self.search(limit=1, offset=0)
        with self.db.get_session() as session:
            paper = session.query(Paper).get(paper_id)
            if not paper:
                return None

            paper_dict = {
                "id": paper.id,
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "journal_or_venue": paper.journal_or_venue,
                "abstract": paper.abstract,
                "doi": paper.doi,
                "main_external_id_type": paper.main_external_id_type,
                "main_external_id_value": paper.main_external_id_value,
                "external_ids": paper.external_ids,
                "source_name": paper.source_name,
                "source_tier": paper.source_tier,
                "source_url": paper.source_url,
                "open_access_flag": paper.open_access_flag,
                "retrieval_status": paper.retrieval_status,
                "created_at": paper.created_at.isoformat(),
                "updated_at": paper.updated_at.isoformat(),
                "files": []
            }

            for file in paper.files:
                paper_dict["files"].append({
                    "id": file.id,
                    "local_path": file.local_path,
                    "checksum": file.checksum,
                    "file_size_bytes": file.file_size_bytes,
                    "mime_type": file.mime_type,
                    "download_url": file.download_url,
                    "download_status": file.download_status,
                    "download_timestamp": file.download_timestamp.isoformat()
                })

            return paper_dict

    def get_statistics(self) -> Dict[str, Any]:
        """Get corpus statistics.

        Returns:
            Dictionary with corpus stats
        """
        with self.db.get_session() as session:
            total_papers = session.query(Paper).count()
            papers_with_pdf = session.query(Paper).join(File).distinct().count()
            total_sources = session.query(Paper.source_name).distinct().count()

            # Papers by year
            papers_by_year = {}
            year_query = session.query(Paper.year, session.query(Paper).filter(Paper.year == Paper.year).count())
            # Simplified: just get count by source
            papers_by_source = {}
            for source_name in session.query(Paper.source_name).distinct():
                count = session.query(Paper).filter(Paper.source_name == source_name[0]).count()
                papers_by_source[source_name[0]] = count

            # Papers by tier
            papers_by_tier = {}
            for tier in [1, 2, 3]:
                count = session.query(Paper).filter(Paper.source_tier == tier).count()
                papers_by_tier[tier] = count

            return {
                "total_papers": total_papers,
                "papers_with_pdf": papers_with_pdf,
                "papers_without_pdf": total_papers - papers_with_pdf,
                "total_sources": total_sources,
                "papers_by_source": papers_by_source,
                "papers_by_tier": papers_by_tier
            }
