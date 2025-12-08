"""PubMed adapter using NCBI E-utilities."""

import logging
import time
from typing import List, Optional
from pymed import PubMed

from src.adapters.base import SourceAdapter, PaperMetadata

logger = logging.getLogger(__name__)


class PubMedAdapter(SourceAdapter):
    """Adapter for PubMed/NCBI database."""

    def __init__(self, email: str, tier: int = 1, rate_limit: float = 3.0):
        """Initialize PubMed adapter.

        Args:
            email: Email for NCBI rate limit compliance
            tier: Source tier (default 1)
            rate_limit: Requests per second
        """
        super().__init__("pubmed", tier, rate_limit)
        self.pubmed = PubMed(tool="Algamol", email=email)
        self.last_request_time = 0
        self.min_interval = 1.0 / rate_limit

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def _extract_metadata(self, article) -> PaperMetadata:
        """Extract metadata from PubMed article object."""
        # Extract authors
        authors = []
        if hasattr(article, 'authors') and article.authors:
            for author in article.authors:
                if hasattr(author, 'lastname') and hasattr(author, 'firstname'):
                    name = f"{author.get('firstname', '')} {author.get('lastname', '')}".strip()
                    if name:
                        authors.append(name)

        # Extract year
        year = None
        if hasattr(article, 'publication_date') and article.publication_date:
            try:
                year = article.publication_date.year
            except:
                pass

        # Extract journal
        journal = None
        if hasattr(article, 'journal') and article.journal:
            journal = article.journal

        # Extract identifiers
        doi = article.doi if hasattr(article, 'doi') else None
        pmid = article.pubmed_id if hasattr(article, 'pubmed_id') else None

        # Build external IDs
        external_ids = {}
        if pmid:
            external_ids['pmid'] = str(pmid)

        # Check for PMC ID
        pmc_id = None
        if hasattr(article, 'pmc_id') and article.pmc_id:
            pmc_id = article.pmc_id
            external_ids['pmcid'] = pmc_id

        # Determine open access status
        open_access = bool(pmc_id)  # If it has PMC ID, it's likely OA

        # Build URLs
        source_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
        pdf_url = None
        oa_locations = []

        if pmc_id:
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
            oa_locations.append({
                "url": pdf_url,
                "version": "publishedVersion",
                "license": "open"
            })

        return PaperMetadata(
            title=article.title if hasattr(article, 'title') else "Unknown Title",
            authors=authors,
            year=year,
            journal_or_venue=journal,
            abstract=article.abstract if hasattr(article, 'abstract') else None,
            doi=doi,
            pmid=pmid,
            pmcid=pmc_id,
            external_ids=external_ids,
            source_name=self.source_name,
            source_tier=self.tier,
            source_url=source_url,
            pdf_url=pdf_url,
            oa_locations=oa_locations,
            open_access=open_access,
        )

    def search(
        self,
        query: str,
        max_results: int = 100,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        **kwargs
    ) -> List[PaperMetadata]:
        """Search PubMed for papers."""
        self._rate_limit()

        # Build query with date filters
        full_query = query
        if year_start and year_end:
            full_query = f"{query} AND ({year_start}:{year_end}[pdat])"
        elif year_start:
            full_query = f"{query} AND ({year_start}:3000[pdat])"
        elif year_end:
            full_query = f"{query} AND (1900:{year_end}[pdat])"

        self.logger.info(f"Searching PubMed: {full_query} (max_results={max_results})")

        try:
            results = self.pubmed.query(full_query, max_results=max_results)
            papers = []

            for article in results:
                try:
                    paper = self._extract_metadata(article)
                    papers.append(paper)
                except Exception as e:
                    self.logger.error(f"Error extracting PubMed article metadata: {e}")
                    continue

            self.logger.info(f"Found {len(papers)} papers from PubMed")
            return papers

        except Exception as e:
            self.logger.error(f"PubMed search error: {e}")
            return []

    def fetch_by_id(self, identifier: str, id_type: Optional[str] = None) -> Optional[PaperMetadata]:
        """Fetch a paper by PMID or DOI."""
        self._rate_limit()

        # Normalize identifier
        identifier = identifier.strip()

        # If DOI, convert to PubMed query
        if id_type == "doi" or (not id_type and "/" in identifier):
            query = f'"{identifier}"[DOI]'
        else:
            # Assume PMID
            query = identifier

        self.logger.debug(f"Fetching from PubMed: {query}")

        try:
            results = list(self.pubmed.query(query, max_results=1))
            if results:
                return self._extract_metadata(results[0])
            return None
        except Exception as e:
            self.logger.error(f"PubMed fetch error for {identifier}: {e}")
            return None

    def supports_id_type(self, id_type: str) -> bool:
        """Check if this adapter supports a given identifier type."""
        return id_type.lower() in ["pmid", "doi"]

    def normalize_identifier(self, identifier: str, id_type: str) -> str:
        """Normalize identifier."""
        identifier = identifier.strip()
        if id_type.lower() == "pmid":
            # Remove any "PMID:" prefix
            if identifier.upper().startswith("PMID:"):
                identifier = identifier[5:].strip()
        return identifier
