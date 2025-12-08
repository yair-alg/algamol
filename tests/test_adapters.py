"""Tests for source adapters."""

import pytest
from src.adapters.base import PaperMetadata
from src.adapters.arxiv_adapter import ArxivAdapter
from src.adapters.crossref import CrossrefAdapter


def test_arxiv_adapter_search():
    """Test arXiv adapter search functionality."""
    adapter = ArxivAdapter(tier=2, rate_limit=1.0)

    # Search for a well-known topic
    results = adapter.search("quantum computing", max_results=5)

    assert len(results) > 0
    assert all(isinstance(r, PaperMetadata) for r in results)

    # Check first result has required fields
    first = results[0]
    assert first.title
    assert first.source_name == "arxiv"
    assert first.source_tier == 2
    assert first.arxiv_id


def test_arxiv_adapter_fetch_by_id():
    """Test arXiv adapter fetch by ID."""
    adapter = ArxivAdapter(tier=2, rate_limit=1.0)

    # Fetch a known arXiv paper
    paper = adapter.fetch_by_id("1706.03762", id_type="arxiv")

    assert paper is not None
    assert "Attention" in paper.title  # "Attention is All You Need"
    assert paper.arxiv_id == "1706.03762"
    assert paper.open_access is True
    assert paper.pdf_url


def test_crossref_adapter_fetch_by_doi():
    """Test Crossref adapter fetch by DOI."""
    adapter = CrossrefAdapter(mailto="test@example.com", tier=1, rate_limit=1.0)

    # Fetch a known DOI
    paper = adapter.fetch_by_id("10.1038/nature12373", id_type="doi")

    assert paper is not None
    assert paper.doi == "10.1038/nature12373"
    assert paper.title
    assert paper.source_name == "crossref"


def test_paper_metadata_primary_id():
    """Test PaperMetadata primary ID extraction."""
    # Test DOI priority
    paper1 = PaperMetadata(
        title="Test Paper",
        source_name="test",
        source_tier=1,
        doi="10.1234/test",
        pmid="12345"
    )
    id_type, id_value = paper1.get_primary_id()
    assert id_type == "doi"
    assert id_value == "10.1234/test"

    # Test PMID when no DOI
    paper2 = PaperMetadata(
        title="Test Paper",
        source_name="test",
        source_tier=1,
        pmid="12345"
    )
    id_type, id_value = paper2.get_primary_id()
    assert id_type == "pmid"
    assert id_value == "12345"

    # Test arXiv ID
    paper3 = PaperMetadata(
        title="Test Paper",
        source_name="test",
        source_tier=1,
        arxiv_id="1234.5678"
    )
    id_type, id_value = paper3.get_primary_id()
    assert id_type == "arxiv"
    assert id_value == "1234.5678"


def test_identifier_normalization():
    """Test identifier normalization."""
    adapter = ArxivAdapter()

    # Test arXiv ID normalization
    assert adapter.normalize_identifier("arxiv:1234.5678", "arxiv") == "1234.5678"
    assert adapter.normalize_identifier("https://arxiv.org/abs/1234.5678", "arxiv") == "1234.5678"

    crossref = CrossrefAdapter(mailto="test@example.com")

    # Test DOI normalization
    assert crossref.normalize_identifier("doi:10.1234/test", "doi") == "10.1234/test"
    assert crossref.normalize_identifier("https://doi.org/10.1234/test", "doi") == "10.1234/test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
