from __future__ import annotations

import typer

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit
from latris.operations import docs as docs_ops


@handle_cli_errors
def docs(
    topic: str = typer.Argument(
        "agents",
        help="agents (guide for AI agents) | readme (whole README) | llms (llms.txt) | foundations (methods).",
    ),
) -> None:
    """Print the documentation that ships with latris — no network needed.

    Start with `latris docs` (the guide for AI agents: building a model,
    reports, the link for a person), then `latris capabilities`. The
    methods-and-foundations reference is `latris docs foundations`, with
    the machine-readable registry behind it in `latris foundations`.
    """
    text = docs_ops.read_docs(topic)
    emit({"topic": topic, "text": text}, human=lambda: typer.echo(text))
