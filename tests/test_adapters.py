from pathlib import Path

import pytest

from src.adapters.base import PaperMetadata
from src.adapters.crossref import CrossrefAdapter
from src.adapters.arxiv_adapter import ArxivAdapter
from src.pipeline import SearchPipeline
from src.database import init_database


@pytest.fixture()
def temp_db(tmp_path: Path):
    """Initialize a temporary database for isolated tests."""
    db_path = tmp_path / "algamol_test.db"
    init_database(db_path)
    return db_path


def test_crossref_metadata_parsing():
    """Ensure Crossref metadata extraction parses core fields."""
    adapter = CrossrefAdapter(mailto="test@example.com", tier=1, rate_limit=10.0)

    work = {
        "title": ["Example Paper Title"],
        "author": [
            {"given": "Jane", "family": "Doe"},
            {"given": "John", "family": "Smith"},
        ],
        "published-print": {"date-parts": [[2023, 6, 1]]},
        "container-title": ["Journal of Testing"],
        "abstract": "<jats:p>Example abstract.</jats:p>",
        "DOI": "10.1234/example.doi",
        "URL": "https://doi.org/10.1234/example.doi",
        "link": [
            {
                "URL": "https://example.org/paper.pdf",
                "content-type": "application/pdf",
            }
        ],
        "license": [
            {"URL": "https://creativecommons.org/licenses/by/4.0/"}
        ],
    }

    metadata = adapter._extract_metadata(work)  # type: ignore[attr-defined]

    assert metadata.title == "Example Paper Title"
    assert metadata.authors == ["Jane Doe", "John Smith"]
    assert metadata.year == 2023
    assert metadata.journal_or_venue == "Journal of Testing"
    assert metadata.doi == "10.1234/example.doi"
    assert metadata.pdf_url == "https://example.org/paper.pdf"
    assert metadata.open_access is True


def test_store_paper_in_db(temp_db: Path):
    """Verify PaperMetadata persists through the pipeline without downloading PDFs."""
    pipeline = SearchPipeline()

    metadata = PaperMetadata(
        title="Stored Paper",
        authors=["Ada Lovelace"],
        year=2024,
        journal_or_venue="Proceedings of Testing",
        doi="10.5555/stored.paper",
        external_ids={"doi": "10.5555/stored.paper"},
        source_name="crossref",
        source_tier=1,
        source_url="https://doi.org/10.5555/stored.paper",
        open_access=True,
    )

    with pipeline.db.get_session() as session:
        paper = pipeline._store_paper(session, metadata, download_pdf=False)
        session.flush()

        retrieved = session.get(type(paper), paper.id)
        assert retrieved is not None
        assert retrieved.title == "Stored Paper"
        assert retrieved.doi == "10.5555/stored.paper"
        assert retrieved.source_name == "crossref"
        assert retrieved.retrieval_status in {"pending", "pdf_available", "no_open_pdf_found"}



def test_identifier_normalization():
    """Adapters should normalize identifiers predictably."""
    arxiv = ArxivAdapter()
    assert arxiv.normalize_identifier("arxiv:1234.5678", "arxiv") == "1234.5678"
    assert arxiv.normalize_identifier("https://arxiv.org/abs/1234.5678", "arxiv") == "1234.5678"

    crossref = CrossrefAdapter(mailto="test@example.com")
    assert crossref.normalize_identifier("doi:10.1234/test", "doi") == "10.1234/test"
    assert crossref.normalize_identifier("https://doi.org/10.1234/test", "doi") == "10.1234/test"
