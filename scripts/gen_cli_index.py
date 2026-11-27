"""Regenerate the "Commands by stage and track" index in docs/engineering/CLI_REFERENCE.md from the places
every command declares (src/latris/operations/places.py). tests/test_places.py fails when it is stale."""

from __future__ import annotations

from pathlib import Path

from latris.operations.places import INDEX_END, INDEX_START, cli_index_markdown

DOC = Path(__file__).resolve().parents[1] / "docs" / "engineering" / "CLI_REFERENCE.md"


def render(text: str) -> str:
    head, _, rest = text.partition(INDEX_START)
    _, _, tail = rest.partition(INDEX_END)
    return f"{head}{INDEX_START}\n\n{cli_index_markdown()}\n{INDEX_END}{tail}"


if __name__ == "__main__":
    DOC.write_text(render(DOC.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {DOC}")
