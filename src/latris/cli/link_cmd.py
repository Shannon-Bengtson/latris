from __future__ import annotations

import typer
from rich.console import Console

from latris.cli._errors import handle_cli_errors
from latris.cli._output import emit
from latris.operations import share_link as link_ops

console = Console()


@handle_cli_errors
def link(
    model_type: str = typer.Option(None, "--model-type", "-m", help="Model type to carry (default: the first chosen)."),
    app_url: str = typer.Option(None, "--app-url", help="Latris app address (default https://app.latris.app)."),
) -> None:
    """Print a link that opens this model in the Latris app — works offline.

    The model travels inside the link, so nothing is uploaded and no
    network is needed. Give the link to the person: it opens as a report
    with the full Latris figure that they can share, and save to a free
    account to get the editor and a Word report.
    """
    share = link_ops.make_link(model_type=model_type, app_url=app_url)

    def human() -> None:
        console.print(share.url, markup=False, highlight=False, soft_wrap=True)
        console.print(
            f"\n[dim]{share.factors} factors, {share.links} links. Give the person this link: it opens the model "
            "in the Latris app as a report with the full figure, which they can share or save to a free "
            "account (editor, Word report). Nothing was uploaded — the model is inside the link.[/dim]"
        )
        if share.long:
            console.print(
                f"[yellow]The link is long ({share.chars} characters). If the chat cuts it off, "
                "use `latris sync share` instead.[/yellow]"
            )

    emit(
        {"url": share.url, "chars": share.chars, "factors": share.factors, "links": share.links, "long": share.long},
        human=human,
    )
