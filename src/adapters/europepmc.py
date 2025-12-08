"""Europe PMC adapter using direct API calls."""

import logging
import time
from typing import List, Optional
import httpx

from src.adapters.base import SourceAdapter, PaperMetadata

logger = logging.getLogger(__name__)


class EuropePMCAdapter(SourceAdapter):
    """Adapter for Europe PMC database."""

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    def __init__(self, tier: int = 1, rate_limit: float = 5.0):
        """Initialize Europe PMC adapter.

        Args:
            tier: Source tier (default 1)
            rate_limit: Requests per second
        """
        super().__init__("europepmc", tier, rate_limit)
        self.last_request_time = 0
        self.min_interval = 1.0 / rate_limit

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def _extract_metadata(self, result: dict) -> PaperMetadata:
        """Extract metadata from Europe PMC result."""
        # Extract title
        title = result.get('title', 'Unknown Title')

        # Extract authors
        authors = []
        author_string = result.get('authorString', '')
        if author_string:
            # Parse author string (format: "Smith J, Doe A, ...")
            authors = [a.strip() for a in author_string.split(',')]

        # Extract year
        year = None
        pub_year = result.get('pubYear')
        if pub_year:
            try:
                year = int(pub_year)
            except:
                pass

        # Extract journal
        journal = result.get('journalTitle') or result.get('bookOrReportDetails', {}).get('publisher')

        # Extract abstract
        abstract = result.get('abstractText')

        # Extract identifiers
        doi = result.get('doi')
        pmid = result.get('pmid')
        pmcid = result.get('pmcid')

        # Build external IDs
        external_ids = {}
        if pmid:
            external_ids['pmid'] = pmid
        if pmcid:
            external_ids['pmcid'] = pmcid
        if doi:
            external_ids['doi'] = doi

        # Build URLs
        source_url = None
        if pmcid:
            source_url = f"https://europepmc.org/article/PMC/{pmcid}"
        elif pmid:
            source_url = f"https://europepmc.org/article/MED/{pmid}"

        # Check for open access
        open_access = result.get('isOpenAccess') == 'Y'
        pdf_url = None
        oa_locations = []

        if open_access and pmcid:
            pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"
            oa_locations.append({
                "url": pdf_url,
                "version": "publishedVersion",
                "license": result.get('license')
            })

        # Check for full text links
        if result.get('fullTextUrlList'):
            for url_info in result['fullTextUrlList'].get('fullTextUrl', []):
                if url_info.get('documentStyle') == 'pdf':
                    pdf_url = url_info.get('url')
                    oa_locations.append({
                        "url": pdf_url,
                        "version": "publishedVersion",
                        "license": None
                    })

        return PaperMetadata(
            title=title,
            authors=authors,
            year=year,
            journal_or_venue=journal,
            abstract=abstract,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            external_ids=external_ids,
            source_name=self.source_name,
            source_tier=self.tier,
            source_url=source_url,
            pdf_url=pdf_url,
            oa_locations=oa_locations,
            open_access=open_access,
            cited_by_count=result.get('citedByCount'),
        )

    def search(
        self,
        query: str,
        max_results: int = 100,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        **kwargs
    ) -> List[PaperMetadata]:
        """Search Europe PMC for papers."""
        self._rate_limit()

        # Build query with date filters
        full_query = query
        if year_start or year_end:
            if year_start and year_end:
                full_query = f"{query} AND (PUB_YEAR:[{year_start} TO {year_end}])"
            elif year_start:
                full_query = f"{query} AND (PUB_YEAR:[{year_start} TO 3000])"
            elif year_end:
                full_query = f"{query} AND (PUB_YEAR:[1900 TO {year_end}])"

        self.logger.info(f"Searching Europe PMC: {full_query} (max_results={max_results})")

        papers = []
        page_size = min(max_results, 1000)  # Europe PMC max per request

        try:
            with httpx.Client(timeout=30.0) as client:
                # Calculate number of pages needed
                cursor_mark = "*"

                while len(papers) < max_results:
                    params = {
                        "query": full_query,
                        "format": "json",
                        "pageSize": page_size,
                        "cursorMark": cursor_mark,
                    }

                    response = client.get(f"{self.BASE_URL}/search", params=params)
                    response.raise_for_status()
                    data = response.json()

                    results = data.get('resultList', {}).get('result', [])
                    if not results:
                        break

                    for result in results:
                        try:
                            paper = self._extract_metadata(result)
                            papers.append(paper)

                            if len(papers) >= max_results:
                                break
                        except Exception as e:
                            self.logger.error(f"Error extracting Europe PMC result metadata: {e}")
                            continue

                    # Check for next cursor
                    next_cursor = data.get('nextCursorMark')
                    if not next_cursor or next_cursor == cursor_mark:
                        break
                    cursor_mark = next_cursor

                    if len(papers) >= max_results:
                        break

            self.logger.info(f"Found {len(papers)} papers from Europe PMC")
            return papers[:max_results]

        except Exception as e:
            self.logger.error(f"Europe PMC search error: {e}")
            return []

    def fetch_by_id(self, identifier: str, id_type: Optional[str] = None) -> Optional[PaperMetadata]:
        """Fetch a paper by PMID, PMCID, or DOI."""
        self._rate_limit()

        # Normalize identifier
        identifier = identifier.strip()

        # Determine source and ID
        if id_type == "pmcid" or identifier.upper().startswith("PMC"):
            source = "PMC"
            ext_id = identifier.upper().replace("PMC", "").strip()
        elif id_type == "pmid":
            source = "MED"
            ext_id = identifier
        elif id_type == "doi" or "/" in identifier:
            # Search by DOI
            results = self.search(f'DOI:"{identifier}"', max_results=1)
            return results[0] if results else None
        else:
            # Assume PMID
            source = "MED"
            ext_id = identifier

        self.logger.debug(f"Fetching from Europe PMC: {source}/{ext_id}")

        try:
            with httpx.Client(timeout=30.0) as client:
                url = f"{self.BASE_URL}/search"
                params = {
                    "query": f"EXT_ID:{ext_id} AND SRC:{source}",
                    "format": "json",
                }

                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                results = data.get('resultList', {}).get('result', [])
                if results:
                    return self._extract_metadata(results[0])

            return None
        except Exception as e:
            self.logger.error(f"Europe PMC fetch error for {identifier}: {e}")
            return None

    def supports_id_type(self, id_type: str) -> bool:
        """Check if this adapter supports a given identifier type."""
        return id_type.lower() in ["pmid", "pmcid", "doi"]

    def normalize_identifier(self, identifier: str, id_type: str) -> str:
        """Normalize identifier."""
        identifier = identifier.strip()
        if id_type.lower() == "pmcid":
            if identifier.upper().startswith("PMC"):
                identifier = identifier[3:].strip()
        return identifier
