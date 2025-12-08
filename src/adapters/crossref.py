"""Crossref adapter using Habanero library."""

import logging
import time
from typing import List, Optional
from habanero import Crossref

from src.adapters.base import SourceAdapter, PaperMetadata

logger = logging.getLogger(__name__)


class CrossrefAdapter(SourceAdapter):
    """Adapter for Crossref DOI registry."""

    def __init__(self, mailto: str, tier: int = 1, rate_limit: float = 50.0):
        """Initialize Crossref adapter.

        Args:
            mailto: Email for polite pool access
            tier: Source tier (default 1)
            rate_limit: Requests per second
        """
        super().__init__("crossref", tier, rate_limit)
        self.cr = Crossref(mailto=mailto)
        self.last_request_time = 0
        self.min_interval = 1.0 / rate_limit

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def _extract_metadata(self, work: dict) -> PaperMetadata:
        """Extract metadata from Crossref work item."""
        # Extract title
        title = work.get('title', ['Unknown Title'])[0] if work.get('title') else "Unknown Title"

        # Extract authors
        authors = []
        for author in work.get('author', []):
            given = author.get('given', '')
            family = author.get('family', '')
            name = f"{given} {family}".strip()
            if name:
                authors.append(name)

        # Extract year
        year = None
        if 'published-print' in work:
            date_parts = work['published-print'].get('date-parts', [[]])[0]
            if date_parts:
                year = date_parts[0]
        elif 'published-online' in work:
            date_parts = work['published-online'].get('date-parts', [[]])[0]
            if date_parts:
                year = date_parts[0]
        elif 'created' in work:
            date_parts = work['created'].get('date-parts', [[]])[0]
            if date_parts:
                year = date_parts[0]

        # Extract journal/venue
        journal = None
        if 'container-title' in work and work['container-title']:
            journal = work['container-title'][0]

        # Extract abstract
        abstract = work.get('abstract')

        # Extract DOI
        doi = work.get('DOI')

        # Build source URL
        source_url = work.get('URL', f"https://doi.org/{doi}" if doi else None)

        # Check for open access links
        open_access = False
        pdf_url = None
        oa_locations = []

        if 'link' in work:
            for link in work['link']:
                if link.get('content-type') == 'application/pdf':
                    pdf_url = link.get('URL')
                    open_access = True
                    oa_locations.append({
                        "url": pdf_url,
                        "version": "publishedVersion",
                        "license": work.get('license', [{}])[0].get('URL') if work.get('license') else None
                    })

        # Check license info for OA status
        if work.get('license'):
            for lic in work['license']:
                if any(oa_indicator in lic.get('URL', '').lower()
                       for oa_indicator in ['creativecommons', 'cc-by', 'open']):
                    open_access = True

        return PaperMetadata(
            title=title,
            authors=authors,
            year=year,
            journal_or_venue=journal,
            abstract=abstract,
            doi=doi,
            external_ids={"doi": doi} if doi else {},
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
        """Search Crossref for papers."""
        self._rate_limit()

        # Build filter
        filter_params = {}
        if year_start:
            filter_params['from-pub-date'] = str(year_start)
        if year_end:
            filter_params['until-pub-date'] = str(year_end)

        self.logger.info(f"Searching Crossref: {query} (max_results={max_results})")

        try:
            # Search with filters
            results = self.cr.works(
                query=query,
                limit=max_results,
                filter=filter_params if filter_params else None
            )

            papers = []
            if results and 'message' in results and 'items' in results['message']:
                for work in results['message']['items']:
                    try:
                        paper = self._extract_metadata(work)
                        papers.append(paper)
                    except Exception as e:
                        self.logger.error(f"Error extracting Crossref work metadata: {e}")
                        continue

            self.logger.info(f"Found {len(papers)} papers from Crossref")
            return papers

        except Exception as e:
            self.logger.error(f"Crossref search error: {e}")
            return []

    def fetch_by_id(self, identifier: str, id_type: Optional[str] = None) -> Optional[PaperMetadata]:
        """Fetch a paper by DOI."""
        self._rate_limit()

        # Normalize DOI
        doi = self.normalize_identifier(identifier, "doi")

        self.logger.debug(f"Fetching from Crossref: {doi}")

        try:
            work = self.cr.works(ids=doi)
            if work and 'message' in work:
                return self._extract_metadata(work['message'])
            return None
        except Exception as e:
            self.logger.error(f"Crossref fetch error for {doi}: {e}")
            return None

    def supports_id_type(self, id_type: str) -> bool:
        """Check if this adapter supports a given identifier type."""
        return id_type.lower() == "doi"

    def normalize_identifier(self, identifier: str, id_type: str) -> str:
        """Normalize DOI."""
        identifier = identifier.strip()
        # Remove common DOI prefixes
        if identifier.lower().startswith("doi:"):
            identifier = identifier[4:].strip()
        if identifier.startswith("https://doi.org/"):
            identifier = identifier[16:].strip()
        if identifier.startswith("http://doi.org/"):
            identifier = identifier[15:].strip()
        if identifier.startswith("https://dx.doi.org/"):
            identifier = identifier[19:].strip()
        if identifier.startswith("http://dx.doi.org/"):
            identifier = identifier[18:].strip()
        return identifier
