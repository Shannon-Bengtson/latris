from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.operations import references as ops

app = typer.Typer(help="Manage the research-base reference library.", no_args_is_help=True)
console = Console()


@app.command("add")
@handle_cli_errors
def add(
    bibkey: str = typer.Argument(..., help="BibTeX-style citation key (unique within the project)."),
    title: str = typer.Option(..., "--title", help="Reference title."),
    author: list[str] = typer.Option(
        None,
        "--author",
        "-a",
        help="Author, 'Last, First' form. Repeat for multiple authors.",
    ),
    year: int = typer.Option(None, "--year", help="Publication year."),
    container: str = typer.Option(None, "--container", help="Journal / conference / book."),
    doi: str = typer.Option(None, "--doi", help="DOI."),
    url: str = typer.Option(None, "--url", help="URL."),
    notes: str = typer.Option(None, "--notes", help="Free-text notes."),
) -> None:
    """Add a reference to the project library."""
    ref, sha = ops.add_reference(
        bibkey,
        title,
        authors=author or [],
        year=year,
        container=container,
        doi=doi,
        url=url,
        notes=notes,
    )
    console.print(f"[green]added[/green] reference [bold]{ref.bibkey}[/bold] · commit [cyan]{sha[:10]}[/cyan]")


@app.command("list")
@handle_cli_errors
def list_() -> None:
    """List references in the project library."""
    refs = ops.list_references()
    if not refs:
        console.print("[dim](no references yet)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Key")
    table.add_column("Year")
    table.add_column("Title")
    table.add_column("Authors")
    for r in refs:
        table.add_row(
            r.bibkey,
            str(r.year) if r.year else "",
            r.title,
            "; ".join(r.authors) if r.authors else "",
        )
    console.print(table)


@app.command("import")
@handle_cli_errors
def import_(
    _: str = typer.Argument(..., help="Path to .bib file (not implemented in v0)."),
) -> None:
    """BibTeX import — deferred. Use `latris ref add` for now."""
    console.print(
        "[yellow]not implemented in v0[/yellow]: BibTeX import lands in a later milestone. "
        "Use `latris ref add <bibkey> --title ...` for now."
    )
    raise typer.Exit(code=2)


@app.command("snapshot")
@handle_cli_errors
def snapshot(
    bibkey: str = typer.Argument(..., help="Reference bibkey to attach a source snapshot to."),
    retrieval_url: str = typer.Option(..., "--url", help="URL the extract was fetched from."),
    extract: str = typer.Option(..., "--extract", help="Captured text (≤ ~2000 chars)."),
    kind: str = typer.Option(
        "abstract",
        "--kind",
        help="Snapshot kind: abstract, landing_page_text, or full_text_excerpt.",
    ),
) -> None:
    """Persist a fetched source snapshot against a reference (Phase 4 will auto-fetch)."""
    if kind not in {"abstract", "landing_page_text", "full_text_excerpt"}:
        raise typer.BadParameter(
            "kind must be one of: abstract, landing_page_text, full_text_excerpt"
        )
    ref, sha = ops.set_source_snapshot(
        bibkey,
        retrieval_url=retrieval_url,
        extract=extract,
        kind=kind,
    )
    console.print(
        f"[green]snapshot set[/green] for [bold]{ref.bibkey}[/bold] "
        f"({kind}) · commit [cyan]{sha[:10]}[/cyan]"
    )


@app.command("fetch")
@handle_cli_errors
def fetch(
    bibkey: str = typer.Argument(..., help="Reference bibkey to fetch full text for."),
    url: str | None = typer.Option(
        None,
        "--url",
        help=(
            "Override the URL to fetch. Defaults to the Reference's "
            "url, or doi.org/<doi> if not set."
        ),
    ),
) -> None:
    """Fetch a reference's full text (Phase 4b — Tier-1 retrieval).

    Stores the extracted text at ``ai/reference-extracts/<bibkey>.txt``
    (gitignored) and updates the Reference's ``source_snapshot`` with
    ``kind=full_text_excerpt``. The verification prompt then reads
    chunks from the artefact instead of the small snapshot extract.
    """
    ref, sha = ops.fetch_reference_source(bibkey, url=url)
    snap = ref.source_snapshot
    chars = len(snap.extract or "") if snap else 0
    console.print(
        f"[green]fetched[/green] [bold]{ref.bibkey}[/bold] "
        f"(extract={chars} chars, kind={snap.kind if snap else 'none'}) · "
        f"commit [cyan]{sha[:10]}[/cyan]"
    )
