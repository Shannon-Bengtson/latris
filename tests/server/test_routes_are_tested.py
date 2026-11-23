"""Guard: every server route is exercised by a test.

A route counts as tested when some test names its path (a literal, or an f-string with its parameters
filled). Routes untested when this guard arrived are listed in ``untested_routes.txt``; the list only
shrinks — a new route needs a test, and a listed route that gains one (or goes) must come off the list.
See docs/engineering/TESTING.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from latris.server import app as app_module
from latris.server.app import create_app

TESTS = Path(__file__).resolve().parents[1]
ALLOWED = Path(__file__).with_name("untested_routes.txt")


def _routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    # latris's own routes only: an installed plugin (the Latris app's, in a
    # shared dev environment) brings routes this repo neither has nor tests.
    monkeypatch.setattr(app_module, "_register_plugins", lambda app: None)
    app = create_app(project_root=tmp_path)
    return [(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops]


def _named_in(path: str, text: str) -> bool:
    parts = re.split(r"\{[^}]+\}", path)
    rx = r"[^\"'\s]*?".join(re.escape(x) for x in parts)
    return re.search(r"[\"'f]" + rx + r"(?:[\"'?]|$)", text, re.M) is not None


def _allowed() -> set[str]:
    return {ln.strip() for ln in ALLOWED.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def test_every_route_is_exercised_by_a_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = "\n".join(p.read_text(encoding="utf-8") for p in TESTS.rglob("*.py") if p.resolve() != Path(__file__).resolve())
    untested = {f"{m} {p}" for m, p in _routes(tmp_path, monkeypatch) if not _named_in(p, text)}
    allowed = _allowed()
    assert sorted(untested - allowed) == [], "write a test for these routes"
    assert sorted(allowed - untested) == [], f"tested now (or gone): take them off {ALLOWED.name}"
