"""Guard: every CLI command appears in the worked example (``worked_example/worked_example.py``).

CLAUDE.md: "A feature that isn't in the worked example isn't done." Commands missing when this guard
arrived are listed in ``worked_example/not_in_worked_example.txt`` — some can't run there (they need real
keys or a network: ``ai key set``, ``sync login``), the rest are owed. The list only shrinks: a new command
must be in the worked example, and a listed one that gets added (or goes) must come off the list.
"""

from __future__ import annotations

import re
from pathlib import Path

import typer.main

from latris.cli.app import app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "worked_example" / "worked_example.py"
ALLOWED = ROOT / "worked_example" / "not_in_worked_example.txt"


def _commands() -> list[str]:
    out: list[str] = []

    def walk(c, prefix: str) -> None:
        subs = getattr(c, "commands", None)
        if subs:
            for name, sub in subs.items():
                walk(sub, f"{prefix} {name}".strip())
        else:
            out.append(prefix)

    walk(typer.main.get_command(app), "")
    return out


def _in_example(command: str, text: str) -> bool:
    words = r"\s*,\s*".join(f'"{re.escape(w)}"' for w in command.split())
    return re.search(r"\[\s*(?:\"--json\",\s*)?" + words, text) is not None


def test_every_command_is_in_the_worked_example() -> None:
    text = EXAMPLE.read_text()
    missing = {c for c in _commands() if not _in_example(c, text)}
    allowed = {ln.strip() for ln in ALLOWED.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    assert sorted(missing - allowed) == [], "add these to worked_example/worked_example.py"
    assert sorted(allowed - missing) == [], f"in the worked example now (or gone): take them off {ALLOWED.name}"
