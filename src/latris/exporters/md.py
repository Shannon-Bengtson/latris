"""Markdown building blocks with no project dependencies.

Shared by the report exporters and by the formalism plugins that render their
own report sections (``operations/formalisms``), so the plugins depend on
this leaf rather than on the exporters that import operations.
"""

from __future__ import annotations

from typing import Any

MAX_ROWS = 8
"""Rows a results table shows before it summarises the rest."""


def fmt(x: Any) -> str:
    """A number to four significant figures; ``—`` for none."""
    if x is None:
        return "—"
    if isinstance(x, float | int):
        return f"{x:.4g}"
    return str(x)


def esc(text: Any) -> str:
    """Text safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(esc(c) for c in row) + " |" for row in rows]
    out.append("")
    return out


def grounding(origin: str | None, verification: str | None) -> str:
    """How far to trust a number, in words: reviewed, or where it came from."""
    if verification == "human-verified":
        return "reviewed"
    who = {"ai-proposed": "AI-proposed", "data-derived": "from data", "human-elicited": "elicited"}.get(
        origin or "", "entered"
    )
    return f"{who}, not yet reviewed"
