# Algamol Quick Start Guide

This guide will get you running Algamol in 5 minutes.

## 1. Install Dependencies

```bash
# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

## 2. Configure

Edit `config.yaml` and add your email (required for API rate limiting):

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

## 3. Initialize Database

```bash
python algamol.py init
```

## 4. Run Your First Search

```bash
# Search for papers on a topic
python algamol.py search-topic "CRISPR gene editing" --max-results 10

# Or search by specific IDs
python algamol.py search-ids --ids "1706.03762,10.1038/nature12373"
```

## 5. Explore Your Corpus

```bash
# List papers
python algamol.py list-papers --limit 10

# View statistics
python algamol.py stats

# Export to CSV
python algamol.py export-index my_papers.csv
```

## 6. Start the API Server (Optional)

```bash
python run_api.py
```

Then visit: http://localhost:8000/docs for interactive API documentation.

## Example Workflow

```bash
# 1. Search for recent papers on machine learning
python algamol.py search-topic "machine learning drug discovery" \
    --year-start 2023 \
    --max-results 20

# 2. List papers with PDFs
python algamol.py list-papers --has-pdf true --limit 20

# 3. Export for analysis
python algamol.py export-index ml_papers.csv

# 4. Search local corpus
python algamol.py list-papers --query "protein" --year-start 2023
```

## What's Happening?

1. **Search**: Queries PubMed, Crossref, arXiv, OpenAlex, and Europe PMC
2. **Download**: Automatically finds and downloads open-access PDFs
3. **Store**: Saves metadata to SQLite and PDFs to `data/papers/`
4. **Deduplicate**: Merges results across sources using DOIs
5. **Track**: Records provenance, checksums, and download status

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Check `data/papers/` for downloaded PDFs
- Inspect `data/algamol.db` with SQLite browser
- Review `data/algamol.log` for detailed logs
- Try the API with `python run_api.py`

## Troubleshooting

**"Email required" errors**: Add your email to `config.yaml`

**No PDFs downloaded**: Many papers are not open access - this is expected

**Rate limit errors**: Reduce `rate_limit_per_second` in config

**Import errors**: Make sure you activated the virtual environment

## Getting Help

- Check logs: `tail -f data/algamol.log`
- View stats: `python algamol.py stats`
- Test adapters: `pytest tests/ -v`

Happy researching! 🔬📚
