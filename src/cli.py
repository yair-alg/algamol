"""Command-line interface for Algamol."""

import logging
import sys
import json
import csv
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import load_config, get_config
from src.database import init_database
from src.pipeline import SearchPipeline
from src.corpus_search import CorpusSearch

app = typer.Typer(help="Algamol - Scientific Literature Collection and Management")
console = Console()


def setup_logging():
    """Setup logging configuration."""
    config = get_config()
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    # File handler
    file_handler = logging.FileHandler(config.logging.file)
    file_handler.setLevel(logging.DEBUG)

    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


@app.command()
def init(
    config_path: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """Initialize the Algamol database and configuration."""
    try:
        console.print("[bold blue]Initializing Algamol...[/bold blue]")

        # Load config
        load_config(config_path)
        config = get_config()

        # Setup logging
        setup_logging()

        # Initialize database
        init_database()

        console.print("[bold green]✓[/bold green] Database initialized")
        console.print(f"[bold green]✓[/bold green] Data directory: {config.get_data_dir()}")
        console.print(f"[bold green]✓[/bold green] Database: {config.get_db_path()}")
        console.print("[bold green]Algamol is ready![/bold green]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@app.command()
def search_topic(
    query: str = typer.Argument(..., help="Search query"),
    max_results: Optional[int] = typer.Option(None, help="Max results per source"),
    year_start: Optional[int] = typer.Option(None, help="Start year"),
    year_end: Optional[int] = typer.Option(None, help="End year"),
    sources: Optional[str] = typer.Option(None, help="Comma-separated source names"),
    no_pdf: bool = typer.Option(False, help="Skip PDF downloads"),
    config_path: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """Search for papers by topic."""
    try:
        load_config(config_path)
        setup_logging()

        console.print(f"[bold blue]Searching for:[/bold blue] {query}")

        pipeline = SearchPipeline()

        source_list = sources.split(",") if sources else None

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Searching sources...", total=None)

            results = pipeline.search_topic(
                query=query,
                max_results_per_source=max_results,
                year_start=year_start,
                year_end=year_end,
                sources=source_list,
                download_pdfs=not no_pdf
            )

        # Display results
        console.print(f"\n[bold green]Search completed![/bold green]")
        console.print(f"Total results: {results['total_results']}")
        console.print(f"New papers: {results['new_papers']}")
        console.print(f"Existing papers: {results['existing_papers']}")
        console.print(f"PDFs downloaded: {results['pdfs_downloaded']}")

        if results['errors']:
            console.print(f"[yellow]Errors: {len(results['errors'])}[/yellow]")
            for error in results['errors']:
                console.print(f"  - {error['source']}: {error['error']}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logging.exception("Search error")
        sys.exit(1)


@app.command()
def search_ids(
    ids_file: Optional[str] = typer.Option(None, help="File with IDs (one per line)"),
    ids: Optional[str] = typer.Option(None, help="Comma-separated IDs"),
    id_type: Optional[str] = typer.Option(None, help="ID type (doi, pmid, arxiv, etc.)"),
    no_pdf: bool = typer.Option(False, help="Skip PDF downloads"),
    config_path: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """Search for papers by identifiers."""
    try:
        load_config(config_path)
        setup_logging()

        # Get identifiers
        identifiers = []
        if ids_file:
            with open(ids_file, 'r') as f:
                identifiers = [line.strip() for line in f if line.strip()]
        elif ids:
            identifiers = [i.strip() for i in ids.split(",")]
        else:
            console.print("[bold red]Error:[/bold red] Must provide --ids-file or --ids")
            sys.exit(1)

        console.print(f"[bold blue]Searching for {len(identifiers)} identifiers[/bold blue]")

        pipeline = SearchPipeline()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching papers...", total=None)

            results = pipeline.search_by_ids(
                identifiers=identifiers,
                id_type=id_type,
                download_pdfs=not no_pdf
            )

        # Display results
        console.print(f"\n[bold green]Search completed![/bold green]")
        console.print(f"Found: {results['total_results']}")
        console.print(f"New papers: {results['new_papers']}")
        console.print(f"Existing papers: {results['existing_papers']}")
        console.print(f"PDFs downloaded: {results['pdfs_downloaded']}")
        console.print(f"Not found: {results['not_found']}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logging.exception("ID search error")
        sys.exit(1)


@app.command()
def list_papers(
    query: Optional[str] = typer.Option(None, help="Text search query"),
    year_start: Optional[int] = typer.Option(None, help="Start year"),
    year_end: Optional[int] = typer.Option(None, help="End year"),
    source_tier: Optional[int] = typer.Option(None, help="Source tier (1, 2, 3)"),
    has_pdf: Optional[bool] = typer.Option(None, help="Filter by PDF availability"),
    source: Optional[str] = typer.Option(None, help="Source name"),
    author: Optional[str] = typer.Option(None, help="Author name search"),
    journal: Optional[str] = typer.Option(None, help="Journal name search"),
    limit: int = typer.Option(20, help="Maximum results"),
    config_path: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """List papers from local corpus."""
    try:
        load_config(config_path)
        setup_logging()

        corpus = CorpusSearch()

        papers = corpus.search(
            query_text=query,
            year_start=year_start,
            year_end=year_end,
            source_tier=source_tier,
            has_pdf=has_pdf,
            source_name=source,
            author=author,
            journal=journal,
            limit=limit
        )

        if not papers:
            console.print("[yellow]No papers found[/yellow]")
            return

        # Display as table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", width=6)
        table.add_column("Year", width=6)
        table.add_column("Title", width=50)
        table.add_column("Authors", width=30)
        table.add_column("PDF", width=5)

        for paper in papers:
            authors_str = ", ".join(paper['authors'][:2]) if paper['authors'] else "N/A"
            if len(paper['authors']) > 2:
                authors_str += "..."

            table.add_row(
                str(paper['id']),
                str(paper['year']) if paper['year'] else "N/A",
                paper['title'][:50] + "..." if len(paper['title']) > 50 else paper['title'],
                authors_str,
                "✓" if paper['files'] else "✗"
            )

        console.print(table)
        console.print(f"\n[bold]Total:[/bold] {len(papers)} papers")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logging.exception("List error")
        sys.exit(1)


@app.command()
def export_index(
    output_file: str = typer.Argument(..., help="Output file path (CSV or JSON)"),
    format: str = typer.Option("csv", help="Export format (csv or json)"),
    config_path: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """Export paper index to CSV or JSON."""
    try:
        load_config(config_path)
        setup_logging()

        corpus = CorpusSearch()

        console.print("[bold blue]Exporting corpus...[/bold blue]")

        # Get all papers
        papers = corpus.search(limit=1000000)  # Get all

        if not papers:
            console.print("[yellow]No papers to export[/yellow]")
            return

        output_path = Path(output_file)

        if format.lower() == "json":
            # Export as JSON
            with open(output_path, 'w') as f:
                json.dump(papers, f, indent=2)

        elif format.lower() == "csv":
            # Export as CSV
            with open(output_path, 'w', newline='') as f:
                fieldnames = [
                    'id', 'title', 'year', 'journal_or_venue', 'doi',
                    'main_external_id_type', 'main_external_id_value',
                    'source_name', 'source_tier', 'source_url',
                    'open_access_flag', 'retrieval_status',
                    'pdf_local_path', 'pdf_checksum', 'pdf_size_bytes'
                ]

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for paper in papers:
                    row = {
                        'id': paper['id'],
                        'title': paper['title'],
                        'year': paper['year'],
                        'journal_or_venue': paper['journal_or_venue'],
                        'doi': paper['doi'],
                        'main_external_id_type': paper['main_external_id_type'],
                        'main_external_id_value': paper['main_external_id_value'],
                        'source_name': paper['source_name'],
                        'source_tier': paper['source_tier'],
                        'source_url': paper['source_url'],
                        'open_access_flag': paper['open_access_flag'],
                        'retrieval_status': paper['retrieval_status'],
                        'pdf_local_path': paper['files'][0]['local_path'] if paper['files'] else '',
                        'pdf_checksum': paper['files'][0]['checksum'] if paper['files'] else '',
                        'pdf_size_bytes': paper['files'][0]['file_size_bytes'] if paper['files'] else ''
                    }
                    writer.writerow(row)
        else:
            console.print(f"[bold red]Error:[/bold red] Unsupported format: {format}")
            sys.exit(1)

        console.print(f"[bold green]✓[/bold green] Exported {len(papers)} papers to {output_path}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logging.exception("Export error")
        sys.exit(1)


@app.command()
def stats(
    config_path: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """Display corpus statistics."""
    try:
        load_config(config_path)
        setup_logging()

        corpus = CorpusSearch()
        stats = corpus.get_statistics()

        console.print("\n[bold blue]Corpus Statistics[/bold blue]\n")
        console.print(f"Total papers: {stats['total_papers']}")
        console.print(f"Papers with PDF: {stats['papers_with_pdf']}")
        console.print(f"Papers without PDF: {stats['papers_without_pdf']}")
        console.print(f"Total sources: {stats['total_sources']}")

        console.print("\n[bold]Papers by source:[/bold]")
        for source, count in stats['papers_by_source'].items():
            console.print(f"  {source}: {count}")

        console.print("\n[bold]Papers by tier:[/bold]")
        for tier, count in stats['papers_by_tier'].items():
            console.print(f"  Tier {tier}: {count}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logging.exception("Stats error")
        sys.exit(1)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
