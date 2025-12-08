"""PDF retrieval and management."""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from slugify import slugify
import httpx

from src.adapters.base import PaperMetadata
from src.config import get_config

logger = logging.getLogger(__name__)


class PDFRetriever:
    """Handles PDF download and storage with provenance tracking."""

    def __init__(self, data_dir: Optional[Path] = None):
        """Initialize PDF retriever.

        Args:
            data_dir: Base data directory. If None, uses config.
        """
        if data_dir is None:
            config = get_config()
            data_dir = config.get_data_dir()

        self.data_dir = data_dir
        self.papers_dir = data_dir / "papers"
        self.papers_dir.mkdir(parents=True, exist_ok=True)

    def _compute_checksum(self, content: bytes) -> str:
        """Compute SHA-256 checksum of content.

        Args:
            content: File content as bytes

        Returns:
            Hexadecimal checksum string
        """
        return hashlib.sha256(content).hexdigest()

    def _generate_filename(self, paper: PaperMetadata, identifier: str) -> str:
        """Generate a structured filename for a paper.

        Args:
            paper: Paper metadata
            identifier: Primary identifier for the paper

        Returns:
            Filename without path
        """
        # Get first author last name
        first_author = "unknown"
        if paper.authors:
            first_author = paper.authors[0].split()[-1]  # Get last name
            first_author = slugify(first_author, max_length=20)

        # Get short title slug
        title_slug = slugify(paper.title, max_length=30)

        # Clean identifier
        id_slug = slugify(identifier.replace("/", "_"), max_length=30)

        # Year
        year = paper.year or "unknown"

        return f"{year}_{first_author}_{title_slug}_{id_slug}.pdf"

    def _get_file_path(self, paper: PaperMetadata, identifier: str) -> Path:
        """Get the full file path for storing a paper.

        Args:
            paper: Paper metadata
            identifier: Primary identifier

        Returns:
            Full path to PDF file
        """
        # Organize by year
        year = paper.year or "unknown"
        year_dir = self.papers_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        filename = self._generate_filename(paper, identifier)
        return year_dir / filename

    def try_unpaywall(self, doi: str, email: str) -> Optional[Dict[str, Any]]:
        """Try to get OA location from Unpaywall API.

        Args:
            doi: DOI of the paper
            email: Email for Unpaywall API

        Returns:
            Dict with OA information or None
        """
        if not doi:
            return None

        url = f"https://api.unpaywall.org/v2/{doi}"
        params = {"email": email}

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('is_oa'):
                        best_oa = data.get('best_oa_location')
                        if best_oa and best_oa.get('url_for_pdf'):
                            return {
                                'pdf_url': best_oa['url_for_pdf'],
                                'version': best_oa.get('version'),
                                'license': best_oa.get('license')
                            }
            return None
        except Exception as e:
            logger.debug(f"Unpaywall lookup failed for {doi}: {e}")
            return None

    def download_pdf(
        self,
        paper: PaperMetadata,
        unpaywall_email: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Download PDF for a paper if legally available.

        Args:
            paper: Paper metadata with potential PDF URLs
            unpaywall_email: Email for Unpaywall API

        Returns:
            Dict with file info or None if download failed/not available
        """
        config = get_config()
        if not config.pdf_retrieval.enabled:
            logger.debug("PDF retrieval is disabled in config")
            return None

        # Get primary identifier
        id_type, identifier = paper.get_primary_id()
        if not identifier:
            logger.warning(f"No primary identifier for paper: {paper.title}")
            return None

        # Try to find a PDF URL
        pdf_url = paper.pdf_url

        # If no PDF URL, try Unpaywall for DOI
        if not pdf_url and paper.doi:
            email = unpaywall_email or config.pdf_retrieval.unpaywall_email
            unpaywall_info = self.try_unpaywall(paper.doi, email)
            if unpaywall_info:
                pdf_url = unpaywall_info['pdf_url']
                logger.info(f"Found PDF via Unpaywall: {pdf_url}")

        # Check OA locations
        if not pdf_url and paper.oa_locations:
            for location in paper.oa_locations:
                if location.get('url'):
                    pdf_url = location['url']
                    break

        if not pdf_url:
            logger.debug(f"No PDF URL available for paper: {identifier}")
            return None

        # Download the PDF
        try:
            logger.info(f"Downloading PDF from: {pdf_url}")

            headers = {
                'User-Agent': config.pdf_retrieval.user_agent
            }

            with httpx.Client(
                timeout=config.pdf_retrieval.timeout_seconds,
                follow_redirects=True
            ) as client:
                response = client.get(pdf_url, headers=headers)
                response.raise_for_status()

                content = response.content

                # Check file size
                max_size = config.pdf_retrieval.max_file_size_mb * 1024 * 1024
                if len(content) > max_size:
                    logger.warning(f"PDF too large ({len(content)} bytes): {pdf_url}")
                    return None

                # Verify it looks like a PDF
                if not content.startswith(b'%PDF'):
                    logger.warning(f"Downloaded content is not a PDF: {pdf_url}")
                    return None

                # Compute checksum
                checksum = self._compute_checksum(content)

                # Generate file path
                file_path = self._get_file_path(paper, identifier)

                # Check if file already exists with same checksum
                if file_path.exists():
                    with open(file_path, 'rb') as f:
                        existing_checksum = self._compute_checksum(f.read())
                    if existing_checksum == checksum:
                        logger.info(f"PDF already exists with same checksum: {file_path}")
                        return {
                            'local_path': str(file_path),
                            'checksum': checksum,
                            'file_size_bytes': len(content),
                            'download_url': pdf_url,
                            'download_status': 'already_exists',
                            'mime_type': 'application/pdf'
                        }

                # Save the file
                with open(file_path, 'wb') as f:
                    f.write(content)

                logger.info(f"PDF downloaded successfully: {file_path}")

                return {
                    'local_path': str(file_path),
                    'checksum': checksum,
                    'file_size_bytes': len(content),
                    'download_url': pdf_url,
                    'download_status': 'success',
                    'mime_type': 'application/pdf'
                }

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error downloading PDF ({e.response.status_code}): {pdf_url}")
            return None
        except httpx.TimeoutException:
            logger.warning(f"Timeout downloading PDF: {pdf_url}")
            return None
        except Exception as e:
            logger.error(f"Error downloading PDF from {pdf_url}: {e}")
            return None

    def verify_file(self, file_path: str, expected_checksum: str) -> bool:
        """Verify a file's integrity using checksum.

        Args:
            file_path: Path to file
            expected_checksum: Expected SHA-256 checksum

        Returns:
            True if file exists and checksum matches
        """
        path = Path(file_path)
        if not path.exists():
            return False

        try:
            with open(path, 'rb') as f:
                actual_checksum = self._compute_checksum(f.read())
            return actual_checksum == expected_checksum
        except Exception as e:
            logger.error(f"Error verifying file {file_path}: {e}")
            return False
