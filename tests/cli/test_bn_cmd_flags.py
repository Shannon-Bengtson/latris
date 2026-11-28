"""`latris bn`: weighted tables, explanations, uncertainty, scenarios and comparisons — flags and errors.

A three-node network: Rain → Wet ← Sprinkler.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project

runner = CliRunner()

pytest.importorskip("pgmpy")


def _ok(*args: str) -> str:
    result = runner.invoke(app, ["bn", *args])
    assert result.exit_code == 0, result.output
    return result.output


def _json(*args: str):
    result = runner.invoke(app, ["--json", "bn", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["result"]


def _fails(*args: str) -> str:
    result = runner.invoke(app, ["bn", *args])
    assert result.exit_code != 0, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result.output.lower()


@pytest.fixture
def net(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "bn"
    init_project(root, statement="Why is the lawn wet?")
    rain, _ = node_ops.add_node("Rain", kind="variable", root=root)
    spr, _ = node_ops.add_node("Sprinkler", kind="variable", root=root)
    wet, _ = node_ops.add_node("Wet", kind="variable", root=root)
    edge_ops.add_edge(rain.id, wet.id, kind="causal", root=root)
    edge_ops.add_edge(spr.id, wet.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    for label in ("Rain", "Sprinkler", "Wet"):
        _ok("set-state-space", label, "yes,no")
    _ok("set-cpt", "Rain", "--probs", "0.2,0.8")
    _ok("set-cpt", "Sprinkler", "--probs", "0.4,0.6")
    _ok("set-weighted", "Wet", "--base", "0.05,0.95", "-w", "Rain=yes:3", "-w", "Sprinkler=yes:2")
    return root


def test_listings_empty(tmp_path: Path, git_identity, monkeypatch) -> None:
    root = tmp_path / "empty"
    init_project(root, statement="?")
    monkeypatch.chdir(root)
    assert _ok("state-spaces").strip()
    assert _ok("cpts").strip()
    assert _ok("uncertainty").strip()
    assert _ok("scenarios").strip()


def test_set_weighted_variants_and_errors(net: Path) -> None:
    entry = _json("set-weighted", "Wet", "--base", "0.1,0.9", "-w", "Rain=yes:1", "--toward", "yes",
                  "--source", "src_1")
    assert entry["rows"]
    assert "--weight must be" in _fails("set-weighted", "Wet", "--base", "0.1,0.9", "-w", "Rain:1")
    assert "not a number" in _fails("set-weighted", "Wet", "--base", "0.1,0.9", "-w", "Rain=yes:lots")
    assert "--base must be" in _fails("set-weighted", "Wet", "--base", "a,b", "-w", "Rain=yes:1")


def test_state_space_edits(net: Path) -> None:
    # A parent's states can't go while a child's table uses them.
    assert "set those tables without it first" in _fails("remove-states", "Rain")
    assert _ok("remove-states", "Wet").strip()
    assert "error" in _fails("remove-states", "Wet")
    _ok("set-state-space", "Wet", "dry,damp,soaked", "--ordered")
    assert "damp" in _ok("state-spaces")
    assert len(_json("state-spaces")) == 3


def test_cpts_and_check_json(net: Path) -> None:
    assert len(_json("cpts")) == 3
    assert _json("check")


def test_query_options(net: Path) -> None:
    out = _ok("query", "-e", "Wet=yes", "-q", "Rain", "--no-record")
    assert "Rain" in out
    payload = _json("query", "--soft", "Rain=yes:0.7", "--likelihood", "Wet=yes:4,no:1", "--set",
                    "Sprinkler=no", "--no-record")
    assert payload
    assert "error" in _fails("query", "-e", "Wet", "--no-record")
    assert "error" in _fails("query", "--soft", "Rain=yes", "--no-record")
    assert "error" in _fails("query", "--likelihood", "Rain=yes", "--no-record")


def test_explain(net: Path) -> None:
    out = _ok("explain", "-e", "Wet=yes", "--no-record")
    assert "Rain" in out and "Sprinkler" in out
    payload = _json("explain", "-e", "Wet=yes", "--over", "Rain", "--no-record")
    assert payload
    assert _ok("explain", "-e", "Wet=yes", "--set", "Sprinkler=no", "--soft", "Rain=yes:0.6").strip()


def test_uncertainty_and_monte_carlo(net: Path) -> None:
    assert "error" in _fails("monte-carlo", "Wet", "--runs", "10", "--no-record")  # nothing uncertain yet
    _ok("set-uncertainty", "Rain", "--n", "20", "--reason", "a rough guess")
    _ok("set-uncertainty", "Wet", "--n", "50", "--row", "Rain=yes,Sprinkler=no")
    assert "Rain" in _ok("uncertainty")
    assert len(_json("uncertainty")) >= 2
    assert "error" in _fails("set-uncertainty", "Rain", "--n", "-1")

    out = _ok("monte-carlo", "Wet", "--state", "yes", "--runs", "20", "--seed", "3", "-e", "Sprinkler=no",
              "--no-record")
    assert "Wet" in out
    payload = _json("monte-carlo", "Rain", "--runs", "10", "--soft", "Rain=yes:0.5", "--likelihood",
                    "Wet=yes:2,no:1", "--set", "Sprinkler=yes", "--no-record")
    assert payload
    assert "recorded" in _ok("monte-carlo", "Wet", "--runs", "10")

    assert _ok("clear-uncertainty", "Rain").strip()
    assert "error" in _fails("clear-uncertainty", "Rain")


def test_sensitivity(net: Path) -> None:
    out = _ok("sensitivity", "Wet", "--state", "yes", "--top", "3", "--no-record")
    assert "Wet" in out or "Rain" in out
    assert _json("sensitivity", "Wet", "-s", "yes", "-e", "Rain=no", "--set", "Sprinkler=yes", "--no-record")
    assert "error" in _fails("sensitivity", "Wet", "-s", "maybe", "--no-record")
    assert _ok("sensitivity", "Wet", "-s", "yes").strip()


def test_scenarios_and_compare(net: Path) -> None:
    _ok("set-scenario", "Dry spell", "-e", "Rain=no", "-d", "No rain all week", "--reason", "forecast")
    _ok("set-scenario", "Dry, sprinkler off", "--extends", "Dry spell", "--set", "Sprinkler=no",
        "--origin", "human-elicited")
    _ok("set-scenario", "New nozzle", "-t", "Wet[Sprinkler=yes]=0.5,0.5", "--soft", "Rain=no:0.9",
        "--likelihood", "Sprinkler=yes:2,no:1")
    listed = _ok("scenarios")
    assert "Dry spell" in listed and "New nozzle" in listed
    assert len(_json("scenarios")) == 3
    assert "error" in _fails("set-scenario", "Bad", "--extends", "Nope", "-e", "Rain=no")

    assert "Wet" in _ok("query", "--scenario", "Dry spell", "--no-record")
    out = _ok("compare", "Wet", "-S", "Dry spell", "-S", "Dry, sprinkler off", "--runs", "0", "--no-record")
    assert "Dry spell" in out
    _ok("set-uncertainty", "Rain", "--n", "20")
    payload = _json("compare", "Wet", "-S", "Dry spell", "-S", "New nozzle", "--state", "yes", "-r", "baseline",
                    "--runs", "10", "--seed", "1", "-e", "Sprinkler=yes", "--no-record")
    assert payload
    assert "recorded" in _ok("compare", "Wet", "-S", "New nozzle", "--runs", "0")
    assert "error" in _fails("compare", "Wet", "-S", "Nope", "--no-record")
    assert _ok("monte-carlo", "Wet", "--scenario", "Dry spell", "--runs", "5", "--no-record").strip()

    _fails("remove-scenario", "Dry spell")  # another scenario extends it
    assert _ok("remove-scenario", "Dry, sprinkler off").strip()
    assert _ok("remove-scenario", "Dry spell").strip()
    assert "error" in _fails("remove-scenario", "Dry spell")
