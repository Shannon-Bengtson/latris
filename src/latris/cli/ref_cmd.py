from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit, json_mode
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
    cited_via: str = typer.Option(
        None, "--cited-via", help="Key of the source you read this one in (e.g. a review quoting a study)."
    ),
) -> None:
    """Add a reference to the project library.

    Give only identifiers you have seen: a DOI recalled from memory is
    worse than none. A source read second-hand (a review describing a
    study) takes `--cited-via <review key>`, and the report says so.
    """
    ref, sha = ops.add_reference(
        bibkey,
        title,
        authors=author or [],
        year=year,
        container=container,
        doi=doi,
        url=url,
        notes=notes,
        cited_via=cited_via,
    )
    emit(
        ref,
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]added[/green] reference [bold]{ref.bibkey}[/bold] · commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


@app.command("edit")
@handle_cli_errors
def edit(
    bibkey: str = typer.Argument(..., help="Key of the reference to correct."),
    title: str = typer.Option(None, "--title"),
    author: list[str] = typer.Option(None, "--author", "-a", help="Replaces the author list. Repeat for several."),
    year: int = typer.Option(None, "--year"),
    container: str = typer.Option(None, "--container"),
    doi: str = typer.Option(None, "--doi", help='Correct the DOI; "" removes it.'),
    url: str = typer.Option(None, "--url", help='Correct the URL; "" removes it.'),
    notes: str = typer.Option(None, "--notes"),
    cited_via: str = typer.Option(None, "--cited-via", help='Key of the source you read it in; "" clears it.'),
) -> None:
    """Correct a reference's details (only the options given change), as a recorded change."""
    ref, sha = ops.update_reference(
        bibkey, title=title, authors=author or None, year=year, container=container,
        doi=doi, url=url, notes=notes, cited_via=cited_via,
    )
    emit(
        ref,
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]updated[/green] reference [bold]{ref.bibkey}[/bold] · commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


@app.command("remove")
@handle_cli_errors
def remove(
    bibkey: str = typer.Argument(..., help="Key of the reference to remove."),
    with_citations: bool = typer.Option(
        False, "--with-citations", help="Also remove the evidence links that cite it (same commit)."
    ),
    rationale: str = typer.Option(None, "--rationale", "-r", help="Why (kept in the history)."),
) -> None:
    """Remove a reference (refused while it is cited, unless --with-citations)."""
    ref, sha = ops.remove_reference(bibkey, with_citations=with_citations, rationale=rationale)
    emit(
        ref,
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]removed[/green] reference [bold]{ref.bibkey}[/bold] · commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


@app.command("list")
@handle_cli_errors
def list_() -> None:
    """List references in the project library."""
    refs = ops.list_references()
    if json_mode():
        emit(refs, human=lambda: None)
        return
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
