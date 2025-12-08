"""OpenAlex adapter using pyalex library."""

import logging
import time
from typing import List, Optional
from pyalex import Works, config as pyalex_config

from src.adapters.base import SourceAdapter, PaperMetadata

logger = logging.getLogger(__name__)


class OpenAlexAdapter(SourceAdapter):
    """Adapter for OpenAlex scholarly database."""

    def __init__(self, email: str, tier: int = 1, rate_limit: float = 10.0):
        """Initialize OpenAlex adapter.

        Args:
            email: Email for polite pool access
            tier: Source tier (default 1)
            rate_limit: Requests per second
        """
        super().__init__("openalex", tier, rate_limit)
        # Configure pyalex for polite pool
        pyalex_config.email = email
        self.last_request_time = 0
        self.min_interval = 1.0 / rate_limit

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def _extract_metadata(self, work: dict) -> PaperMetadata:
        """Extract metadata from OpenAlex work item."""
        # Extract title
        title = work.get('title', 'Unknown Title')

        # Extract authors
        authors = []
        for authorship in work.get('authorships', []):
            author = authorship.get('author', {})
            name = author.get('display_name')
            if name:
                authors.append(name)

        # Extract year
        year = work.get('publication_year')

        # Extract journal/venue
        journal = None
        if work.get('primary_location'):
            source = work['primary_location'].get('source')
            if source:
                journal = source.get('display_name')

        # Extract abstract (inverted index)
        abstract = None
        if work.get('abstract_inverted_index'):
            # Reconstruct abstract from inverted index
            inverted = work['abstract_inverted_index']
            words = {}
            for word, positions in inverted.items():
                for pos in positions:
                    words[pos] = word
            if words:
                abstract = ' '.join(words[i] for i in sorted(words.keys()))

        # Extract identifiers
        doi = work.get('doi')
        if doi and doi.startswith('https://doi.org/'):
            doi = doi[16:]

        openalex_id = work.get('id')
        if openalex_id and openalex_id.startswith('https://openalex.org/'):
            openalex_id = openalex_id[21:]

        # Build external IDs
        external_ids = {}
        if openalex_id:
            external_ids['openalex'] = openalex_id
        if doi:
            external_ids['doi'] = doi

        # Extract IDs from ids dict
        ids = work.get('ids', {})
        pmid = ids.get('pmid')
        if pmid:
            pmid = pmid.replace('https://pubmed.ncbi.nlm.nih.gov/', '')
            external_ids['pmid'] = pmid

        # Build URLs
        source_url = work.get('id', f"https://openalex.org/{openalex_id}" if openalex_id else None)

        # Check for open access
        open_access = False
        oa_status = work.get('open_access', {}).get('oa_status')
        pdf_url = None
        oa_locations = []

        if work.get('open_access'):
            oa_info = work['open_access']
            open_access = oa_info.get('is_oa', False)
            pdf_url = oa_info.get('oa_url')

        if work.get('best_oa_location'):
            best_oa = work['best_oa_location']
            if not pdf_url:
                pdf_url = best_oa.get('pdf_url') or best_oa.get('landing_page_url')
            oa_locations.append({
                "url": pdf_url,
                "version": best_oa.get('version'),
                "license": best_oa.get('license')
            })

        return PaperMetadata(
            title=title,
            authors=authors,
            year=year,
            journal_or_venue=journal,
            abstract=abstract,
            doi=doi,
            openalex_id=openalex_id,
            pmid=pmid,
            external_ids=external_ids,
            source_name=self.source_name,
            source_tier=self.tier,
            source_url=source_url,
            pdf_url=pdf_url,
            oa_locations=oa_locations,
            open_access=open_access,
            oa_status=oa_status,
            cited_by_count=work.get('cited_by_count'),
        )

    def search(
        self,
        query: str,
        max_results: int = 100,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        **kwargs
    ) -> List[PaperMetadata]:
        """Search OpenAlex for papers."""
        self._rate_limit()

        self.logger.info(f"Searching OpenAlex: {query} (max_results={max_results})")

        try:
            # Build query with filters
            search = Works().search(query)

            if year_start:
                search = search.filter(from_publication_date=f"{year_start}-01-01")
            if year_end:
                search = search.filter(to_publication_date=f"{year_end}-12-31")

            # Paginate to get results
            papers = []
            page = 1
            per_page = min(max_results, 200)  # OpenAlex max per page

            while len(papers) < max_results:
                results = search.paginate(page=page, per_page=per_page)

                if not results:
                    break

                for work in results:
                    try:
                        paper = self._extract_metadata(work)
                        papers.append(paper)

                        if len(papers) >= max_results:
                            break
                    except Exception as e:
                        self.logger.error(f"Error extracting OpenAlex work metadata: {e}")
                        continue

                if len(results) < per_page:
                    break

                page += 1

            self.logger.info(f"Found {len(papers)} papers from OpenAlex")
            return papers[:max_results]

        except Exception as e:
            self.logger.error(f"OpenAlex search error: {e}")
            return []

    def fetch_by_id(self, identifier: str, id_type: Optional[str] = None) -> Optional[PaperMetadata]:
        """Fetch a paper by OpenAlex ID, DOI, or PMID."""
        self._rate_limit()

        # Normalize identifier
        identifier = identifier.strip()

        self.logger.debug(f"Fetching from OpenAlex: {identifier} (type={id_type})")

        try:
            # Build filter based on ID type
            if id_type == "doi" or (not id_type and "/" in identifier):
                # Search by DOI
                doi = identifier
                if not doi.startswith("10."):
                    doi = doi.replace("https://doi.org/", "")
                work_result = Works().filter(doi=doi).get()
            elif id_type == "pmid":
                # Search by PMID
                pmid_url = f"https://pubmed.ncbi.nlm.nih.gov/{identifier}"
                work_result = Works().filter(pmid=pmid_url).get()
            elif id_type == "openalex" or identifier.startswith("W"):
                # Direct OpenAlex ID lookup
                if not identifier.startswith("https://"):
                    identifier = f"https://openalex.org/{identifier}"
                work_result = Works()[identifier]
            else:
                # Try as OpenAlex ID
                work_result = Works()[f"https://openalex.org/{identifier}"]

            if work_result:
                # Handle both single result and list
                if isinstance(work_result, list):
                    if work_result:
                        return self._extract_metadata(work_result[0])
                else:
                    return self._extract_metadata(work_result)

            return None
        except Exception as e:
            self.logger.error(f"OpenAlex fetch error for {identifier}: {e}")
            return None

    def supports_id_type(self, id_type: str) -> bool:
        """Check if this adapter supports a given identifier type."""
        return id_type.lower() in ["doi", "pmid", "openalex"]

    def normalize_identifier(self, identifier: str, id_type: str) -> str:
        """Normalize identifier."""
        identifier = identifier.strip()
        if id_type.lower() == "openalex":
            if identifier.startswith("https://openalex.org/"):
                identifier = identifier[21:]
        return identifier
