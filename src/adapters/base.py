"""Base adapter interface for scholarly sources."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PaperMetadata:
    """Standardized metadata for a scientific paper."""

    # Required fields
    title: str
    source_name: str
    source_tier: int

    # Core metadata
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    journal_or_venue: Optional[str] = None
    abstract: Optional[str] = None

    # Identifiers
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None
    external_ids: Dict[str, str] = field(default_factory=dict)

    # URLs
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    oa_locations: List[Dict[str, Any]] = field(default_factory=list)

    # Access status
    open_access: bool = False
    oa_status: Optional[str] = None  # "gold", "green", "hybrid", "bronze", "closed"

    # Additional metadata
    cited_by_count: Optional[int] = None
    publication_date: Optional[str] = None

    def get_primary_id(self) -> tuple[Optional[str], Optional[str]]:
        """Get the primary identifier type and value.

        Returns:
            Tuple of (id_type, id_value)
        """
        if self.doi:
            return ("doi", self.doi)
        elif self.pmid:
            return ("pmid", self.pmid)
        elif self.arxiv_id:
            return ("arxiv", self.arxiv_id)
        elif self.openalex_id:
            return ("openalex", self.openalex_id)
        elif self.pmcid:
            return ("pmcid", self.pmcid)
        else:
            return (None, None)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "title": self.title,
            "abstract": self.abstract,
            "year": self.year,
            "journal_or_venue": self.journal_or_venue,
            "authors": self.authors,
            "doi": self.doi,
            "source_name": self.source_name,
            "source_tier": self.source_tier,
            "source_url": self.source_url,
            "open_access_flag": self.open_access,
            "external_ids": {
                **self.external_ids,
                "pmid": self.pmid,
                "pmcid": self.pmcid,
                "arxiv_id": self.arxiv_id,
                "openalex_id": self.openalex_id,
            },
        }


class SourceAdapter(ABC):
    """Abstract base class for scholarly source adapters."""

    def __init__(self, source_name: str, tier: int, rate_limit: float = 1.0):
        """Initialize adapter.

        Args:
            source_name: Name of the source (e.g., "pubmed")
            tier: Source tier (1=peer-reviewed/official, 2=preprints, 3=other)
            rate_limit: Maximum requests per second
        """
        self.source_name = source_name
        self.tier = tier
        self.rate_limit = rate_limit
        self.logger = logging.getLogger(f"{__name__}.{source_name}")

    @abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 100,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        **kwargs
    ) -> List[PaperMetadata]:
        """Search for papers by topic query.

        Args:
            query: Free-text search query
            max_results: Maximum number of results to return
            year_start: Start year for filtering
            year_end: End year for filtering
            **kwargs: Additional source-specific parameters

        Returns:
            List of PaperMetadata objects
        """
        pass

    @abstractmethod
    def fetch_by_id(self, identifier: str, id_type: Optional[str] = None) -> Optional[PaperMetadata]:
        """Fetch a single paper by its identifier.

        Args:
            identifier: The identifier value (e.g., DOI, PMID)
            id_type: Type of identifier (e.g., "doi", "pmid"). If None, adapter should try to infer.

        Returns:
            PaperMetadata if found, None otherwise
        """
        pass

    def batch_fetch_by_ids(self, identifiers: List[str], id_type: Optional[str] = None) -> List[PaperMetadata]:
        """Fetch multiple papers by their identifiers.

        Default implementation calls fetch_by_id for each identifier.
        Subclasses can override for more efficient batch operations.

        Args:
            identifiers: List of identifier values
            id_type: Type of identifiers

        Returns:
            List of PaperMetadata objects (may be fewer than input if some not found)
        """
        results = []
        for identifier in identifiers:
            try:
                paper = self.fetch_by_id(identifier, id_type)
                if paper:
                    results.append(paper)
            except Exception as e:
                self.logger.error(f"Error fetching {identifier}: {e}")
        return results

    def supports_id_type(self, id_type: str) -> bool:
        """Check if this adapter supports a given identifier type.

        Args:
            id_type: Identifier type (e.g., "doi", "pmid")

        Returns:
            True if supported
        """
        return False

    def normalize_identifier(self, identifier: str, id_type: str) -> str:
        """Normalize an identifier to canonical form.

        Args:
            identifier: Raw identifier
            id_type: Type of identifier

        Returns:
            Normalized identifier
        """
        return identifier.strip()
