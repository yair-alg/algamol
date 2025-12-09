"""Main search pipeline orchestrating adapters, deduplication, and storage."""

import logging
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from sqlalchemy.orm import Session

from src.config import get_config, SourceConfig, Config
from src.database import get_db, Database
from src.models import Paper, File, Query, QueryResult
from src.adapters import (
    SourceAdapter, PaperMetadata,
    PubMedAdapter, CrossrefAdapter, ArxivAdapter,
    OpenAlexAdapter, EuropePMCAdapter
)
from src.pdf_retriever import PDFRetriever

logger = logging.getLogger(__name__)


class SearchPipeline:
    """Orchestrates paper search, deduplication, and storage."""

    def __init__(
        self,
        config: Optional[Config] = None,
        db: Optional[Database] = None,
        pdf_retriever: Optional[PDFRetriever] = None,
    ):
        """Initialize the search pipeline.

        Dependency injection is supported to simplify testing and
        allow callers to provide pre-configured database instances
        or alternative PDF storage locations.
        """

        self.config = config or get_config()
        self.db = db or get_db()
        self.pdf_retriever = pdf_retriever or PDFRetriever(
            data_dir=self.config.get_data_dir()
        )
        self.adapters: Dict[str, SourceAdapter] = {}
        self._init_adapters()

    def _init_adapters(self):
        """Initialize all enabled source adapters."""
        for source_name, source_config in self.config.sources.items():
            if not source_config.enabled:
                continue

            try:
                if source_name == "pubmed":
                    adapter = PubMedAdapter(
                        email=source_config.email or "user@example.com",
                        tier=source_config.tier,
                        rate_limit=source_config.rate_limit_per_second
                    )
                elif source_name == "crossref":
                    adapter = CrossrefAdapter(
                        mailto=source_config.mailto or source_config.email or "user@example.com",
                        tier=source_config.tier,
                        rate_limit=source_config.rate_limit_per_second
                    )
                elif source_name == "arxiv":
                    adapter = ArxivAdapter(
                        tier=source_config.tier,
                        rate_limit=source_config.rate_limit_per_second
                    )
                elif source_name == "openalex":
                    adapter = OpenAlexAdapter(
                        email=source_config.email or "user@example.com",
                        tier=source_config.tier,
                        rate_limit=source_config.rate_limit_per_second
                    )
                elif source_name == "europepmc":
                    adapter = EuropePMCAdapter(
                        tier=source_config.tier,
                        rate_limit=source_config.rate_limit_per_second
                    )
                else:
                    logger.warning(f"Unknown source: {source_name}")
                    continue

                self.adapters[source_name] = adapter
                logger.info(f"Initialized adapter: {source_name}")

            except Exception as e:
                logger.error(f"Failed to initialize {source_name} adapter: {e}")

    def _find_existing_paper(self, session: Session, metadata: PaperMetadata) -> Optional[Paper]:
        """Find existing paper in database by identifiers.

        Args:
            session: Database session
            metadata: Paper metadata

        Returns:
            Existing Paper object or None
        """
        # Try DOI first
        if metadata.doi:
            paper = session.query(Paper).filter_by(doi=metadata.doi).first()
            if paper:
                return paper

        # Try other identifiers
        if metadata.pmid:
            paper = session.query(Paper).filter(
                Paper.main_external_id_type == "pmid",
                Paper.main_external_id_value == metadata.pmid
            ).first()
            if paper:
                return paper

        if metadata.arxiv_id:
            paper = session.query(Paper).filter(
                Paper.main_external_id_type == "arxiv",
                Paper.main_external_id_value == metadata.arxiv_id
            ).first()
            if paper:
                return paper

        if metadata.openalex_id:
            paper = session.query(Paper).filter(
                Paper.main_external_id_type == "openalex",
                Paper.main_external_id_value == metadata.openalex_id
            ).first()
            if paper:
                return paper

        return None

    def _store_paper(self, session: Session, metadata: PaperMetadata, download_pdf: bool = True) -> Paper:
        """Store or update paper in database.

        Args:
            session: Database session
            metadata: Paper metadata
            download_pdf: Whether to attempt PDF download

        Returns:
            Paper object
        """
        # Check if paper already exists
        existing = self._find_existing_paper(session, metadata)

        id_type, id_value = metadata.get_primary_id()

        if existing:
            # Update existing paper
            logger.debug(f"Updating existing paper: {existing.id}")
            existing.title = metadata.title
            existing.abstract = metadata.abstract or existing.abstract
            existing.year = metadata.year or existing.year
            existing.journal_or_venue = metadata.journal_or_venue or existing.journal_or_venue
            existing.authors = metadata.authors or existing.authors
            existing.updated_at = datetime.utcnow()

            # Merge external IDs
            if existing.external_ids:
                existing.external_ids.update(metadata.external_ids)
            else:
                existing.external_ids = metadata.external_ids

            paper = existing
        else:
            # Create new paper
            logger.debug(f"Creating new paper: {metadata.title[:50]}...")
            paper = Paper(
                title=metadata.title,
                abstract=metadata.abstract,
                year=metadata.year,
                journal_or_venue=metadata.journal_or_venue,
                authors=metadata.authors,
                doi=metadata.doi,
                main_external_id_type=id_type,
                main_external_id_value=id_value,
                external_ids=metadata.external_ids,
                source_name=metadata.source_name,
                source_tier=metadata.source_tier,
                source_url=metadata.source_url,
                open_access_flag=metadata.open_access,
                retrieval_status="pending"
            )
            session.add(paper)
            session.flush()  # Get the paper ID

        # Try to download PDF if enabled and not already present
        if download_pdf and not paper.files:
            pdf_info = self.pdf_retriever.download_pdf(metadata)
            if pdf_info:
                # Check if file already exists by checksum
                existing_file = session.query(File).filter_by(
                    checksum=pdf_info['checksum']
                ).first()

                if not existing_file:
                    file_record = File(
                        paper_id=paper.id,
                        local_path=pdf_info['local_path'],
                        checksum=pdf_info['checksum'],
                        file_size_bytes=pdf_info['file_size_bytes'],
                        mime_type=pdf_info['mime_type'],
                        download_url=pdf_info['download_url'],
                        download_status=pdf_info['download_status']
                    )
                    session.add(file_record)
                    paper.retrieval_status = "pdf_available"
                    logger.info(f"PDF stored for paper {paper.id}")
                else:
                    logger.debug(f"PDF already exists with same checksum")
                    paper.retrieval_status = "pdf_available"
            else:
                paper.retrieval_status = "no_open_pdf_found"
        elif paper.files:
            paper.retrieval_status = "pdf_available"

        return paper

    def search_topic(
        self,
        query: str,
        max_results_per_source: Optional[int] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        sources: Optional[List[str]] = None,
        download_pdfs: bool = True
    ) -> Dict[str, Any]:
        """Search for papers by topic across configured sources.

        Args:
            query: Free-text search query
            max_results_per_source: Max results per source
            year_start: Start year filter
            year_end: End year filter
            sources: List of source names to use (None = all enabled)
            download_pdfs: Whether to download PDFs

        Returns:
            Dict with search results and statistics
        """
        logger.info(f"Starting topic search: '{query}'")

        # Use defaults from config
        if max_results_per_source is None:
            max_results_per_source = self.config.search_defaults.max_results_per_source
        if year_start is None:
            year_start = self.config.search_defaults.year_range_start
        if year_end is None:
            year_end = self.config.search_defaults.year_range_end

        # Determine which sources to use
        if sources is None:
            sources = list(self.adapters.keys())
        else:
            sources = [s for s in sources if s in self.adapters]

        # Create query record
        with self.db.get_session() as session:
            query_record = Query(
                query_type="topic-search",
                raw_query_text=query,
                filters_json={
                    "max_results_per_source": max_results_per_source,
                    "year_start": year_start,
                    "year_end": year_end,
                },
                sources_used=sources,
                execution_status="running"
            )
            session.add(query_record)
            session.flush()
            query_id = query_record.id

        # Search each source
        all_metadata: List[PaperMetadata] = []
        errors = []

        for source_name in sources:
            adapter = self.adapters.get(source_name)
            if not adapter:
                continue

            try:
                logger.info(f"Searching {source_name}...")
                results = adapter.search(
                    query=query,
                    max_results=max_results_per_source,
                    year_start=year_start,
                    year_end=year_end
                )
                all_metadata.extend(results)
                logger.info(f"Got {len(results)} results from {source_name}")
            except Exception as e:
                error_msg = f"Error searching {source_name}: {e}"
                logger.error(error_msg)
                errors.append({"source": source_name, "error": str(e)})

        # Store papers and deduplicate
        with self.db.get_session() as session:
            query_record = session.query(Query).get(query_id)

            new_papers = 0
            existing_papers = 0
            pdfs_downloaded = 0
            seen_ids: Set[str] = set()

            for rank, metadata in enumerate(all_metadata, 1):
                # Simple deduplication by primary ID
                id_type, id_value = metadata.get_primary_id()
                if id_value and id_value in seen_ids:
                    continue
                if id_value:
                    seen_ids.add(id_value)

                # Store paper
                is_new = self._find_existing_paper(session, metadata) is None
                paper = self._store_paper(session, metadata, download_pdf=download_pdfs)

                if is_new:
                    new_papers += 1
                else:
                    existing_papers += 1

                if paper.files:
                    pdfs_downloaded += 1

                # Create query result link
                query_result = QueryResult(
                    query_id=query_id,
                    paper_id=paper.id,
                    rank=rank,
                    source_name=metadata.source_name
                )
                session.add(query_result)

            # Update query record
            query_record.execution_status = "completed"
            query_record.total_results = len(all_metadata)
            query_record.new_papers = new_papers
            query_record.existing_papers = existing_papers
            query_record.pdfs_downloaded = pdfs_downloaded
            query_record.errors_count = len(errors)
            query_record.error_log = errors if errors else None

        logger.info(f"Search completed: {new_papers} new, {existing_papers} existing, {pdfs_downloaded} PDFs")

        return {
            "query_id": query_id,
            "total_results": len(all_metadata),
            "new_papers": new_papers,
            "existing_papers": existing_papers,
            "pdfs_downloaded": pdfs_downloaded,
            "errors": errors
        }

    def search_by_ids(
        self,
        identifiers: List[str],
        id_type: Optional[str] = None,
        download_pdfs: bool = True
    ) -> Dict[str, Any]:
        """Search for papers by identifiers.

        Args:
            identifiers: List of identifiers
            id_type: Type of identifiers (or None to auto-detect)
            download_pdfs: Whether to download PDFs

        Returns:
            Dict with search results and statistics
        """
        logger.info(f"Starting ID search: {len(identifiers)} identifiers")

        # Create query record
        with self.db.get_session() as session:
            query_record = Query(
                query_type="id-list",
                raw_query_text=", ".join(identifiers[:10]) + ("..." if len(identifiers) > 10 else ""),
                filters_json={
                    "id_type": id_type,
                    "count": len(identifiers)
                },
                sources_used=list(self.adapters.keys()),
                execution_status="running"
            )
            session.add(query_record)
            session.flush()
            query_id = query_record.id

        # Process each identifier
        all_metadata: List[PaperMetadata] = []
        errors = []

        for identifier in identifiers:
            found = False

            # Try each adapter
            for source_name, adapter in self.adapters.items():
                if id_type and not adapter.supports_id_type(id_type):
                    continue

                try:
                    logger.debug(f"Trying {source_name} for {identifier}")
                    result = adapter.fetch_by_id(identifier, id_type)
                    if result:
                        all_metadata.append(result)
                        found = True
                        break
                except Exception as e:
                    logger.debug(f"Error fetching from {source_name}: {e}")

            if not found:
                error_msg = f"Could not find paper with ID: {identifier}"
                logger.warning(error_msg)
                errors.append({"identifier": identifier, "error": "not_found"})

        # Store papers
        with self.db.get_session() as session:
            query_record = session.query(Query).get(query_id)

            new_papers = 0
            existing_papers = 0
            pdfs_downloaded = 0

            for rank, metadata in enumerate(all_metadata, 1):
                is_new = self._find_existing_paper(session, metadata) is None
                paper = self._store_paper(session, metadata, download_pdf=download_pdfs)

                if is_new:
                    new_papers += 1
                else:
                    existing_papers += 1

                if paper.files:
                    pdfs_downloaded += 1

                # Create query result link
                query_result = QueryResult(
                    query_id=query_id,
                    paper_id=paper.id,
                    rank=rank,
                    source_name=metadata.source_name
                )
                session.add(query_result)

            # Update query record
            query_record.execution_status = "completed"
            query_record.total_results = len(all_metadata)
            query_record.new_papers = new_papers
            query_record.existing_papers = existing_papers
            query_record.pdfs_downloaded = pdfs_downloaded
            query_record.errors_count = len(errors)
            query_record.error_log = errors if errors else None

        logger.info(f"ID search completed: {new_papers} new, {existing_papers} existing")

        return {
            "query_id": query_id,
            "total_results": len(all_metadata),
            "new_papers": new_papers,
            "existing_papers": existing_papers,
            "pdfs_downloaded": pdfs_downloaded,
            "errors": errors,
            "not_found": len(errors)
        }
