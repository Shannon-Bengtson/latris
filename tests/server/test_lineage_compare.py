"""Comparing versions over HTTP and from the CLI."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations.init import init_project
from latris.operations.lineage import create_milestone, ensure_root_lineage
from latris.operations.nodes import add_node
from latris.server.app import create_app


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "p"
    init_project(root, statement="What drives demand?")
    ensure_root_lineage(root)
    add_node("Price", root=root)
    create_milestone("First draft", root=root)
    add_node("Demand", root=root)
    return root


def test_route_says_what_changed_and_to_what(tmp_path: Path, git_identity) -> None:
    root = _project(tmp_path)
    events = TestClient(create_app(project_root=root)).get(
        "/api/lineage/compare", params={"a": "First draft", "b": "main"}
    ).json()
    added = next(e for e in events if e["kind"] == "node_added")
    assert added["change"] == "added" and added["target_id"].startswith("node_")


def test_cli_groups_the_changes(tmp_path: Path, git_identity, monkeypatch) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    out = CliRunner().invoke(app, ["version", "compare", "First draft", "main"])
    assert out.exit_code == 0, out.output
    assert "Added (1)" in out.output and 'Added node "Demand"' in out.output
    js = CliRunner().invoke(app, ["--json", "version", "compare", "First draft", "main"])
    assert any(e["change"] == "added" and e["kind"] == "node_added" for e in json.loads(js.output)["result"])
