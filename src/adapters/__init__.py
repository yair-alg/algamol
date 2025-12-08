"""Source adapters for scholarly databases and repositories."""

from src.adapters.base import SourceAdapter, PaperMetadata
from src.adapters.pubmed import PubMedAdapter
from src.adapters.crossref import CrossrefAdapter
from src.adapters.arxiv_adapter import ArxivAdapter
from src.adapters.openalex import OpenAlexAdapter
from src.adapters.europepmc import EuropePMCAdapter

__all__ = [
    "SourceAdapter",
    "PaperMetadata",
    "PubMedAdapter",
    "CrossrefAdapter",
    "ArxivAdapter",
    "OpenAlexAdapter",
    "EuropePMCAdapter",
]
