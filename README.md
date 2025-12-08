# Algamol

**Algamol** is a local-first scientific literature collection and management system. It automates the discovery, retrieval, and indexing of peer-reviewed papers from credible sources, storing both metadata and original PDF files in a structured, queryable database.

## Features

- **Multi-source search**: Query PubMed, Crossref, arXiv, OpenAlex, and Europe PMC simultaneously
- **Legal PDF downloads**: Automatically discovers and downloads open-access PDFs via official APIs and Unpaywall
- **Local-first**: All data stored in local SQLite database with organized file structure
- **Deduplication**: Intelligent deduplication across sources using DOIs and other identifiers
- **Provenance tracking**: Complete audit trail with checksums, source URLs, and timestamps
- **CLI and HTTP API**: Use via command-line or integrate with other tools/agents
- **Full-text search**: Fast search across titles, abstracts, and metadata
- **Export capabilities**: Export corpus to CSV or JSON for downstream analysis

## Architecture

```
algamol/
├── src/
│   ├── adapters/        # Source adapters for scholarly APIs
│   ├── config.py        # Configuration management
│   ├── database.py      # SQLAlchemy ORM and DB management
│   ├── models.py        # Database models
│   ├── pipeline.py      # Search orchestration
│   ├── pdf_retriever.py # PDF download and storage
│   ├── corpus_search.py # Local corpus search
│   ├── cli.py          # Command-line interface
│   └── api.py          # FastAPI HTTP service
├── data/
│   ├── papers/         # Downloaded PDFs organized by year
│   └── algamol.db      # SQLite database
├── config.yaml         # Configuration file
└── requirements.txt    # Python dependencies
```

## Installation

### Prerequisites

- Python 3.11 or higher
- pip and virtualenv

### Setup

1. **Clone or download the project**:
   ```bash
   cd algamol
   ```

2. **Create a virtual environment**:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Algamol**:
   Edit `config.yaml` to set your email addresses (required for API rate limiting) and other preferences:
   ```yaml
   sources:
     pubmed:
       email: "your-email@example.com"
     crossref:
       mailto: "your-email@example.com"
     openalex:
       email: "your-email@example.com"

   pdf_retrieval:
     unpaywall_email: "your-email@example.com"
   ```

5. **Initialize the database**:
   ```bash
   python -m src.cli init
   ```

## Usage

### Command-Line Interface

#### Initialize Database
```bash
python -m src.cli init
```

#### Search by Topic
Search for papers on a specific topic:
```bash
python -m src.cli search-topic "machine learning in drug discovery" \
    --max-results 50 \
    --year-start 2020 \
    --year-end 2024
```

#### Search by Identifiers
Fetch papers by DOIs, PMIDs, or arXiv IDs:
```bash
# Single ID
python -m src.cli search-ids --ids "10.1038/nature12373"

# Multiple IDs
python -m src.cli search-ids --ids "10.1038/nature12373,1706.03762,25760607"

# From file (one ID per line)
python -m src.cli search-ids --ids-file my_papers.txt --id-type doi
```

#### List Papers
Query your local corpus:
```bash
# List recent papers
python -m src.cli list-papers --limit 20

# Search by keyword
python -m src.cli list-papers --query "CRISPR" --has-pdf true

# Filter by year and source
python -m src.cli list-papers --year-start 2023 --source pubmed

# Search by author
python -m src.cli list-papers --author "Smith" --limit 10
```

#### Export Index
Export your corpus for analysis:
```bash
# Export as CSV
python -m src.cli export-index corpus.csv --format csv

# Export as JSON
python -m src.cli export-index corpus.json --format json
```

#### View Statistics
```bash
python -m src.cli stats
```

### HTTP API

Start the API server:
```bash
python -m src.api
```

Or with uvicorn:
```bash
uvicorn src.api:app --host 127.0.0.1 --port 8000
```

#### API Endpoints

**Health Check**:
```bash
curl http://localhost:8000/
```

**Search by Topic**:
```bash
curl -X POST http://localhost:8000/search/topic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quantum computing",
    "max_results_per_source": 20,
    "year_start": 2020,
    "download_pdfs": true
  }'
```

**Search by IDs**:
```bash
curl -X POST http://localhost:8000/search/ids \
  -H "Content-Type: application/json" \
  -d '{
    "identifiers": ["10.1038/nature12373", "1706.03762"],
    "download_pdfs": true
  }'
```

**List Papers**:
```bash
curl "http://localhost:8000/papers?query=CRISPR&has_pdf=true&limit=10"
```

**Get Single Paper**:
```bash
curl http://localhost:8000/papers/1
```

**Get Statistics**:
```bash
curl http://localhost:8000/stats
```

**List Sources**:
```bash
curl http://localhost:8000/sources
```

## Configuration

Key configuration options in `config.yaml`:

### Data Storage
```yaml
data_dir: "./data"
database:
  path: "./data/algamol.db"
```

### Source Configuration
Enable/disable sources and set rate limits:
```yaml
sources:
  pubmed:
    enabled: true
    tier: 1
    rate_limit_per_second: 3
    email: "your-email@example.com"
```

### PDF Retrieval
```yaml
pdf_retrieval:
  enabled: true
  unpaywall_email: "your-email@example.com"
  timeout_seconds: 30
  max_file_size_mb: 50
```

### Search Defaults
```yaml
search_defaults:
  max_results_per_source: 100
  year_range_start: 2000
  year_range_end: 2025
```

## Data Schema

### Papers Table
- Core metadata: title, abstract, authors, year, journal
- Identifiers: DOI, PMID, PMC ID, arXiv ID, OpenAlex ID
- Source tracking: source name, tier, URL
- Access status: open access flag, retrieval status

### Files Table
- Local path, checksum (SHA-256), file size
- Download URL, timestamp, status
- Linked to papers via foreign key

### Queries Table
- Query text, filters, execution timestamp
- Results summary: total, new, existing, PDFs downloaded
- Error log for failed operations

## Source Tiers

- **Tier 1**: Peer-reviewed journals, official repositories (PubMed, Crossref, OpenAlex, Europe PMC)
- **Tier 2**: Reputable preprint servers (arXiv)
- **Tier 3**: Other sources (disabled by default)

## File Organization

PDFs are stored in a structured hierarchy:
```
data/papers/
├── 2023/
│   ├── 2023_smith_machine_learning_10.1038.pdf
│   └── 2023_jones_quantum_computing_1234.5678.pdf
├── 2024/
│   └── 2024_doe_crispr_25760607.pdf
└── unknown/
    └── unknown_author_title_id.pdf
```

## Testing

Run tests:
```bash
pytest tests/ -v
```

## Logging

Logs are written to:
- Console: INFO level by default
- File: `data/algamol.log` (DEBUG level)

Configure in `config.yaml`:
```yaml
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "./data/algamol.log"
```

## Legal and Ethical Use

Algamol is designed for **legal and ethical use only**:

- Uses official APIs and documented endpoints
- Respects robots.txt and rate limits
- Downloads only legally accessible open-access PDFs
- Never attempts to bypass paywalls or authentication
- Provides proper attribution and provenance tracking

**Important**: Ensure you comply with the terms of service of each source and respect copyright laws.

## LLM Agent Integration

Algamol is designed as a backend service for LLM agents:

1. **Deterministic API**: All endpoints return structured JSON
2. **Provenance**: Every record includes source and retrieval metadata
3. **File Access**: API returns local file paths for LLM processing
4. **Export**: CSV/JSON export for feeding into RAG pipelines
5. **Search**: Full-text and structured search for context retrieval

Example LLM agent workflow:
```python
import httpx

# Search for papers
response = httpx.post("http://localhost:8000/search/topic", json={
    "query": "recent advances in immunotherapy",
    "year_start": 2023,
    "max_results_per_source": 10
})
result = response.json()

# Get papers with PDFs
papers = httpx.get("http://localhost:8000/papers?has_pdf=true").json()

# Agent can now process PDFs and metadata
for paper in papers:
    pdf_path = paper["files"][0]["local_path"]
    # Process PDF with LLM...
```

## Troubleshooting

### Rate Limiting Errors
- Reduce `rate_limit_per_second` in config.yaml
- Add delays between large batch operations

### PDF Download Failures
- Check internet connectivity
- Verify Unpaywall email in config
- Some papers may not be open access

### Database Errors
- Ensure `data/` directory is writable
- Try `python -m src.cli init` to reinitialize

### API Connection Errors
- Verify source APIs are accessible
- Check email configuration for polite pools

## Contributing

This is a production-ready research tool. Key extension points:

1. **New adapters**: Implement `SourceAdapter` interface in `src/adapters/`
2. **PDF sources**: Extend `PDFRetriever` with new OA discovery methods
3. **Export formats**: Add new formats to `cli.py` export command
4. **Search ranking**: Enhance `CorpusSearch` with relevance scoring

## License

This project uses multiple open-source libraries. Ensure compliance with their licenses:
- SQLAlchemy (MIT)
- FastAPI (MIT)
- Habanero (MIT)
- pyalex (MIT)
- arxiv (MIT)
- pymed (MIT)

## Support

For issues, questions, or contributions, please refer to the project documentation or contact the maintainer.

## Version

Current version: **1.0.0**

Built with Python 3.11, designed for scientific research and LLM agent integration.
