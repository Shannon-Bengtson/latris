"""Tests for the global ``latris --json`` flag (cli/_output.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations.init import init_project

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Does price drive demand?")
    monkeypatch.chdir(root)
    return root


def _json(args: list[str]) -> tuple[int, dict]:
    result = runner.invoke(app, ["--json", *args])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, result.stdout
    return result.exit_code, json.loads(lines[0])


def test_mutations_return_result_and_commit(project: Path) -> None:
    code, price = _json(["node", "add", "Price", "--kind", "variable"])
    assert code == 0
    assert price["result"]["label"] == "Price"
    assert len(price["commit_sha"]) == 40

    _json(["node", "add", "Demand", "--kind", "variable"])
    # Edges resolve their endpoints by label, so a caller never needs the ids.
    code, edge = _json(["edge", "add", "Price", "Demand"])
    assert code == 0
    assert edge["result"]["from_id"] == price["result"]["id"]

    code, pol = _json(["view", "set", "cld", edge["result"]["id"], "polarity", "-"])
    assert code == 0
    assert pol["result"] == {
        "target_id": edge["result"]["id"],
        "model_type": "cld",
        "attribute": "polarity",
        "value": "-",
    }

    code, ref = _json(["ref", "add", "smith2021", "--title", "Price elasticity", "--year", "2021"])
    assert code == 0 and ref["result"]["bibkey"] == "smith2021"
    code, link = _json(["evidence", "add", edge["result"]["id"], "polarity", "smith2021"])
    assert code == 0 and link["result"]["target_id"] == edge["result"]["id"]


def test_listings_return_arrays(project: Path) -> None:
    _json(["node", "add", "Price"])
    code, nodes = _json(["node", "list"])
    assert code == 0
    assert [n["label"] for n in nodes["result"]] == ["Price"]
    assert "commit_sha" not in nodes
    code, edges = _json(["edge", "list"])
    assert code == 0 and edges["result"] == []
    code, refs = _json(["ref", "list"])
    assert code == 0 and refs["result"] == []


def test_errors_are_json_with_exit_codes(project: Path) -> None:
    code, err = _json(["node", "show", "nonexistent"])
    assert code == 1
    assert err["type"] == "resolve error"
    assert err["error"]

    code, err = _json(["evidence", "add", "x", "polarity", "k", "--verified-by", "robot"])
    assert code == 2
    assert "verified-by" in err["error"]


def test_without_flag_output_stays_human(project: Path) -> None:
    result = runner.invoke(app, ["node", "add", "Price"])
    assert result.exit_code == 0
    assert result.stdout.startswith("added")


def test_view_set_accepts_negative_numbers_after_separator(project: Path) -> None:
    _json(["node", "add", "Price"])
    _json(["node", "add", "Demand"])
    _, edge = _json(["edge", "add", "Price", "Demand"])
    code, out = _json(["view", "set", "fcm", edge["result"]["id"], "weight", "--", "-0.7"])
    assert code == 0
    assert out["result"]["value"] == "-0.7"
