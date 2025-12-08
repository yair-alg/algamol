"""FastAPI HTTP service for Algamol."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query as QueryParam
from fastapi.responses import JSONResponse

from src.config import load_config, get_config
from src.database import init_database
from src.pipeline import SearchPipeline
from src.corpus_search import CorpusSearch

# Initialize
try:
    load_config()
    config = get_config()

    # Setup logging
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.logging.file),
            logging.StreamHandler()
        ]
    )

    # Initialize database
    init_database()
except Exception as e:
    logging.error(f"Failed to initialize API: {e}")
    raise

# Create FastAPI app
app = FastAPI(
    title="Algamol API",
    description="Scientific Literature Collection and Management API",
    version="1.0.0"
)

# Initialize services
pipeline = SearchPipeline()
corpus = CorpusSearch()

logger = logging.getLogger(__name__)


# Request/Response models
class TopicSearchRequest(BaseModel):
    """Request model for topic search."""
    query: str = Field(..., description="Search query")
    max_results_per_source: Optional[int] = Field(None, description="Max results per source")
    year_start: Optional[int] = Field(None, description="Start year filter")
    year_end: Optional[int] = Field(None, description="End year filter")
    sources: Optional[List[str]] = Field(None, description="List of source names to search")
    download_pdfs: bool = Field(True, description="Whether to download PDFs")


class IDSearchRequest(BaseModel):
    """Request model for ID-based search."""
    identifiers: List[str] = Field(..., description="List of identifiers")
    id_type: Optional[str] = Field(None, description="Type of identifiers (doi, pmid, arxiv, etc.)")
    download_pdfs: bool = Field(True, description="Whether to download PDFs")


class SearchResponse(BaseModel):
    """Response model for search operations."""
    query_id: int
    total_results: int
    new_papers: int
    existing_papers: int
    pdfs_downloaded: int
    errors: List[Dict[str, Any]] = []


class PaperResponse(BaseModel):
    """Response model for paper data."""
    id: int
    title: str
    authors: Optional[List[str]]
    year: Optional[int]
    journal_or_venue: Optional[str]
    abstract: Optional[str]
    doi: Optional[str]
    main_external_id_type: Optional[str]
    main_external_id_value: Optional[str]
    source_name: str
    source_tier: int
    source_url: Optional[str]
    open_access_flag: bool
    retrieval_status: str
    created_at: str
    files: List[Dict[str, Any]] = []


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    version: str
    timestamp: str


# API endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/search/topic", response_model=SearchResponse)
async def search_topic(request: TopicSearchRequest):
    """Search for papers by topic.

    This endpoint queries configured scholarly sources for papers matching
    the given query, stores metadata in the database, and optionally downloads PDFs.
    """
    try:
        logger.info(f"Topic search request: {request.query}")

        results = pipeline.search_topic(
            query=request.query,
            max_results_per_source=request.max_results_per_source,
            year_start=request.year_start,
            year_end=request.year_end,
            sources=request.sources,
            download_pdfs=request.download_pdfs
        )

        return SearchResponse(**results)

    except Exception as e:
        logger.error(f"Topic search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/ids", response_model=SearchResponse)
async def search_ids(request: IDSearchRequest):
    """Search for papers by identifiers.

    This endpoint resolves a list of identifiers (DOIs, PMIDs, arXiv IDs, etc.)
    by querying configured sources, storing metadata, and optionally downloading PDFs.
    """
    try:
        logger.info(f"ID search request: {len(request.identifiers)} identifiers")

        results = pipeline.search_by_ids(
            identifiers=request.identifiers,
            id_type=request.id_type,
            download_pdfs=request.download_pdfs
        )

        return SearchResponse(**results)

    except Exception as e:
        logger.error(f"ID search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/papers", response_model=List[PaperResponse])
async def list_papers(
    query: Optional[str] = QueryParam(None, description="Text search query"),
    year_start: Optional[int] = QueryParam(None, description="Start year filter"),
    year_end: Optional[int] = QueryParam(None, description="End year filter"),
    source_tier: Optional[int] = QueryParam(None, description="Source tier filter (1, 2, 3)"),
    has_pdf: Optional[bool] = QueryParam(None, description="Filter by PDF availability"),
    source_name: Optional[str] = QueryParam(None, description="Source name filter"),
    author: Optional[str] = QueryParam(None, description="Author name search"),
    journal: Optional[str] = QueryParam(None, description="Journal name search"),
    limit: int = QueryParam(100, description="Maximum results"),
    offset: int = QueryParam(0, description="Result offset for pagination")
):
    """Search local corpus.

    This endpoint searches the local database of papers with various filters.
    Returns a list of papers with metadata and file information.
    """
    try:
        logger.info(f"Corpus search: query={query}, limit={limit}")

        papers = corpus.search(
            query_text=query,
            year_start=year_start,
            year_end=year_end,
            source_tier=source_tier,
            has_pdf=has_pdf,
            source_name=source_name,
            author=author,
            journal=journal,
            limit=limit,
            offset=offset
        )

        return [PaperResponse(**paper) for paper in papers]

    except Exception as e:
        logger.error(f"Corpus search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/papers/{paper_id}", response_model=PaperResponse)
async def get_paper(paper_id: int):
    """Get a single paper by ID.

    Returns full metadata and file information for a specific paper.
    """
    try:
        logger.info(f"Get paper: {paper_id}")

        paper = corpus.get_paper_by_id(paper_id)

        if not paper:
            raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

        return PaperResponse(**paper)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get paper error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_statistics():
    """Get corpus statistics.

    Returns statistics about the local paper corpus including counts by source,
    tier, and PDF availability.
    """
    try:
        logger.info("Get statistics")
        stats = corpus.get_statistics()
        return JSONResponse(content=stats)

    except Exception as e:
        logger.error(f"Statistics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sources")
async def list_sources():
    """List configured sources.

    Returns information about all enabled scholarly sources.
    """
    try:
        sources = []
        for name, adapter in pipeline.adapters.items():
            sources.append({
                "name": name,
                "tier": adapter.tier,
                "rate_limit": adapter.rate_limit
            })
        return JSONResponse(content={"sources": sources})

    except Exception as e:
        logger.error(f"List sources error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "src.api:app",
        host=config.api.host,
        port=config.api.port,
        reload=False
    )
