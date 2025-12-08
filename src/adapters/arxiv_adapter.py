"""arXiv adapter using arxiv library."""

import logging
import time
from typing import List, Optional
import arxiv

from src.adapters.base import SourceAdapter, PaperMetadata

logger = logging.getLogger(__name__)


class ArxivAdapter(SourceAdapter):
    """Adapter for arXiv preprint repository."""

    def __init__(self, tier: int = 2, rate_limit: float = 1.0):
        """Initialize arXiv adapter.

        Args:
            tier: Source tier (default 2 for preprints)
            rate_limit: Requests per second
        """
        super().__init__("arxiv", tier, rate_limit)
        self.client = arxiv.Client()
        self.last_request_time = 0
        self.min_interval = 1.0 / rate_limit

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def _extract_metadata(self, result: arxiv.Result) -> PaperMetadata:
        """Extract metadata from arXiv result."""
        # Extract authors
        authors = [author.name for author in result.authors]

        # Extract year
        year = result.published.year if result.published else None

        # Extract arXiv ID
        arxiv_id = result.entry_id.split("/")[-1]

        # Build URLs
        source_url = result.entry_id
        pdf_url = result.pdf_url

        # arXiv papers are all open access
        oa_locations = [{
            "url": pdf_url,
            "version": "submittedVersion",
            "license": "arxiv"
        }]

        # Extract DOI if available
        doi = result.doi

        # Build external IDs
        external_ids = {"arxiv": arxiv_id}
        if doi:
            external_ids["doi"] = doi

        return PaperMetadata(
            title=result.title,
            authors=authors,
            year=year,
            journal_or_venue=result.journal_ref or "arXiv",
            abstract=result.summary,
            doi=doi,
            arxiv_id=arxiv_id,
            external_ids=external_ids,
            source_name=self.source_name,
            source_tier=self.tier,
            source_url=source_url,
            pdf_url=pdf_url,
            oa_locations=oa_locations,
            open_access=True,
            oa_status="green",
        )

    def search(
        self,
        query: str,
        max_results: int = 100,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        **kwargs
    ) -> List[PaperMetadata]:
        """Search arXiv for papers."""
        self._rate_limit()

        self.logger.info(f"Searching arXiv: {query} (max_results={max_results})")

        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance
            )

            papers = []
            for result in self.client.results(search):
                try:
                    paper = self._extract_metadata(result)

                    # Apply year filtering (arXiv API doesn't support date filters directly)
                    if year_start and paper.year and paper.year < year_start:
                        continue
                    if year_end and paper.year and paper.year > year_end:
                        continue

                    papers.append(paper)
                except Exception as e:
                    self.logger.error(f"Error extracting arXiv result metadata: {e}")
                    continue

            self.logger.info(f"Found {len(papers)} papers from arXiv")
            return papers

        except Exception as e:
            self.logger.error(f"arXiv search error: {e}")
            return []

    def fetch_by_id(self, identifier: str, id_type: Optional[str] = None) -> Optional[PaperMetadata]:
        """Fetch a paper by arXiv ID."""
        self._rate_limit()

        # Normalize identifier
        arxiv_id = self.normalize_identifier(identifier, "arxiv")

        self.logger.debug(f"Fetching from arXiv: {arxiv_id}")

        try:
            search = arxiv.Search(id_list=[arxiv_id])
            results = list(self.client.results(search))

            if results:
                return self._extract_metadata(results[0])
            return None
        except Exception as e:
            self.logger.error(f"arXiv fetch error for {arxiv_id}: {e}")
            return None

    def supports_id_type(self, id_type: str) -> bool:
        """Check if this adapter supports a given identifier type."""
        return id_type.lower() == "arxiv"

    def normalize_identifier(self, identifier: str, id_type: str) -> str:
        """Normalize arXiv identifier."""
        identifier = identifier.strip()
        # Remove common prefixes
        if identifier.lower().startswith("arxiv:"):
            identifier = identifier[6:].strip()
        if identifier.startswith("https://arxiv.org/abs/"):
            identifier = identifier[22:].strip()
        if identifier.startswith("http://arxiv.org/abs/"):
            identifier = identifier[21:].strip()
        return identifier
