from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit
from latris.operations import evidence as ops

app = typer.Typer(
    help="Attach citations to claims (`add`), record whether each source supports its claim (`check`), "
    "and detach a citation (`remove`).",
    no_args_is_help=True,
)
console = Console()


@app.command("add")
@handle_cli_errors
def add(
    target: str = typer.Argument(..., help="Factor (label or ID) or link (\"From -> To\" or edge ID)."),
    attribute: str = typer.Argument(..., help="Attribute name (e.g. description, polarity)."),
    bibkey: str = typer.Argument(..., help="Existing reference key."),
    verified_by: str = typer.Option(
        "human",
        "--verified-by",
        help="human | ai — who attached the citation. Whether the source supports the claim is "
        "recorded separately, with `latris evidence check`.",
    ),
    notes: str = typer.Option(None, "--notes", help="Free-text notes on the link."),
    contradicts: bool = typer.Option(
        False, "--contradicts", help="The source argues against this claim (evidence against, not for)."
    ),
) -> None:
    """Attach a citation to a (target, attribute) pair.

    Sources against a link go on the same link with ``--contradicts``;
    reports then show the evidence for and against it.
    """
    if verified_by not in {"human", "ai"}:
        raise ValueError("--verified-by must be 'human' or 'ai'.")
    link, sha = ops.add_evidence(
        target,
        attribute,
        bibkey,
        verified_by=verified_by,  # type: ignore[arg-type]
        notes=notes,
        contradicts=contradicts,
    )
    emit(
        link,
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]attached[/green] {bibkey} → {link.target_id[:15]}…/{attribute} · commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


# What a reader calls each verdict → the stored value.
_VERDICTS = {
    "supports": "supports",
    "against": "contradicts",
    "off-topic": "orthogonal",
    "too-little": "insufficient_extract",
    "unchecked": "unverified",
}


@app.command("check")
@handle_cli_errors
def check(
    target: str = typer.Argument(..., help="Factor (label or ID) or link (\"From -> To\" or edge ID)."),
    attribute: str = typer.Argument(..., help="Attribute the citation is on (e.g. polarity)."),
    bibkey: str = typer.Argument(..., help="Reference key of the citation."),
    verdict: str = typer.Argument(
        ...,
        help="supports | against | off-topic | too-little (the text seen was too short to tell) | unchecked.",
    ),
    rationale: str = typer.Option(..., "--rationale", "-r", help="What the source says, in a sentence."),
    quote: str = typer.Option(
        None, "--quote",
        help="A passage copied from the source (20+ characters). It is looked up in the text Latris holds "
        "for the source (`ref snapshot`, `ref fetch`, the abstract); an AI's quote that isn't found is refused.",
    ),
    by: str = typer.Option("human", "--by", help="human | ai — who read the source."),
) -> None:
    """Record whether a source actually supports the claim it's cited for.

    Attaching a citation (`evidence add`) records only that it was attached;
    reports count it as "not yet checked against the source" until someone
    reads the source and runs this. An AI agent that read the source passes
    `--by ai`, and for `supports` a `--quote` copied from text Latris holds
    (save what you read with `latris ref snapshot` first). The report says
    what each check rests on: the full text, an excerpt, or the abstract.
    A person's check is the default; their quote is recorded even when
    Latris doesn't hold the text, marked as not found.
    """
    if verdict not in _VERDICTS:
        raise ValueError(f"verdict must be one of: {', '.join(_VERDICTS)}")
    if by not in {"human", "ai"}:
        raise ValueError("--by must be 'human' or 'ai'.")
    link, sha = ops.set_evidence_support_verdict(
        target,
        attribute,
        bibkey,
        new_verdict=_VERDICTS[verdict],  # type: ignore[arg-type]
        rationale=rationale,
        quote=quote,
        checked_by=by,  # type: ignore[arg-type]
    )
    emit(
        link,
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]checked[/green] {bibkey} on {link.target_id[:15]}…/{attribute}: {verdict} · "
            f"commit [cyan]{sha[:10]}[/cyan]"
        ),
    )


@app.command("remove")
@handle_cli_errors
def remove(
    target: str = typer.Argument(..., help="Factor (label or ID) or link (\"From -> To\" or edge ID)."),
    attribute: str = typer.Argument(..., help="Attribute the citation is on (e.g. polarity)."),
    bibkey: str = typer.Argument(..., help="Reference key of the citation."),
    rationale: str = typer.Option(None, "--rationale", "-r", help="Why (kept in the history)."),
) -> None:
    """Detach a citation from a claim, as a recorded change."""
    link, sha = ops.remove_evidence(target, attribute, bibkey, rationale=rationale)
    emit(
        link,
        commit_sha=sha,
        human=lambda: console.print(
            f"[green]removed[/green] {bibkey} from {(link.target_id or 'model')[:15]}…/{attribute} · "
            f"commit [cyan]{sha[:10]}[/cyan]"
        ),
    )
