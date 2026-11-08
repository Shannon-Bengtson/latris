"""`--json` output for the analysis and quantitative commands — what agents (and the
hosted MCP server's named tools) read instead of rich tables."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as va
from latris.operations.init import init_project

runner = CliRunner()


def _json(*args: str) -> dict:
    r = runner.invoke(app, ["--json", *args])
    assert r.exit_code == 0, r.stdout
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture
def loop(tmp_path: Path, git_identity, monkeypatch) -> Path:
    """Workload -> Burnout -> Departures -> Workload, all '+'."""
    root = tmp_path / "p"
    init_project(root, statement="Why do people leave?")
    ids = [node_ops.add_node(n, kind="variable", root=root)[0].id for n in ("Workload", "Burnout", "Departures")]
    for a, b in zip(ids, ids[1:] + ids[:1], strict=True):
        edge, _ = edge_ops.add_edge(a, b, kind="causal", root=root)
        va.set_view_attribute(edge.id, "cld", "polarity", "+", root=root)
    monkeypatch.chdir(root)
    return root


def test_graph_analyses(loop: Path) -> None:
    loops = _json("analyse", "loops")["result"]
    assert loops[0]["type"] == "R" and set(loops[0]["variables"]) == {"Workload", "Burnout", "Departures"}
    effects = _json("analyse", "propagate", "Workload")["result"]["effects"]
    assert {e["variable"]: e["effect"] for e in effects}["Departures"] == "+"
    paths = _json("analyse", "paths", "Workload", "Departures")["result"]["paths"]
    assert [n["variable"] for n in paths[0]["nodes"]] == ["Workload", "Burnout", "Departures"]
    assert "blanket" in _json("analyse", "blanket", "Burnout")["result"]


def test_dag_identification(tmp_path: Path, git_identity, monkeypatch) -> None:
    root = tmp_path / "dag"
    init_project(root, statement="Does training cut turnover?")
    n = {x: node_ops.add_node(x, kind="variable", root=root)[0].id for x in ("Size", "Training", "Turnover")}
    for a, b in (("Size", "Training"), ("Size", "Turnover"), ("Training", "Turnover")):
        edge_ops.add_edge(n[a], n[b], kind="causal", root=root)
    monkeypatch.chdir(root)
    assert _json("analyse", "adjustment-sets", "Training", "Turnover")["result"]["adjustment_sets"] == [["Size"]]
    sep = _json("analyse", "d-sep", "Training", "Turnover", "--given", "Size")["result"]
    assert sep["d_separated"] is False and sep["given"] == ["Size"]


def test_fcm(loop: Path) -> None:
    _json("fcm", "set-weight", "Workload→Burnout", "0.8")
    weights = _json("fcm", "weights")["result"]
    assert {w["link"]: w["weight"] for w in weights}["Workload -> Burnout"] == 0.8
    run = _json("fcm", "infer", "--clamp", "Workload=1.0")["result"]
    assert {a["variable"]: a["clamped"] for a in run["activations"]}["Workload"] is True


def test_bn(tmp_path: Path, git_identity, monkeypatch) -> None:
    pytest.importorskip("pgmpy")
    root = tmp_path / "bn"
    init_project(root, statement="Will it be wet?")
    rain = node_ops.add_node("Rain", kind="variable", root=root)[0]
    wet = node_ops.add_node("Wet", kind="variable", root=root)[0]
    edge_ops.add_edge(rain.id, wet.id, kind="causal", root=root)
    monkeypatch.chdir(root)

    assert _json("bn", "check")["result"]["ready"] is False
    _json("bn", "set-state-space", "Rain", "yes,no")
    _json("bn", "set-state-space", "Wet", "yes,no")
    _json("bn", "set-cpt", "Rain", "--probs", "0.2,0.8")
    assert "commit_sha" in _json("bn", "set-cpt", "Wet", "--parents", "Rain", "--probs", "0.9,0.1,0.1,0.9")
    assert _json("bn", "check")["result"]["ready"] is True
    assert _json("bn", "state-spaces")["result"][0]["states"] == ["yes", "no"]
    cpts = {c["node"]: c for c in _json("bn", "cpts")["result"]}
    assert cpts["Wet"]["rows"][0]["given"] == {"Rain": "yes"}
    post = _json("bn", "query", "-e", "Rain=yes", "-q", "Wet")["result"]
    assert post["given"] == {"Rain": "yes"} and post["marginals"]["Wet"]["yes"] == pytest.approx(0.9)
    assert _json("bn", "marginals")["result"]["marginals"]["Rain"]["yes"] == pytest.approx(0.2)
    sens = _json("bn", "sensitivity", "Wet", "--state", "yes", "--no-record")["result"]
    assert sens["target"] == "Wet" and sens["parameters"]

    # Queries are recorded: the latest of each (query, evidence) shows in reports, with its priors.
    _json("bn", "query", "-e", "Rain=yes", "-q", "Wet")
    shown = _json("results", "list")["result"]
    assert sorted(r["kind"] for r in shown) == ["bn-query", "bn-query"]  # the query + the prior marginals
    from latris.operations import analysis_results as ar

    query = next(r for r in ar.report_results(root=root) if r.payload["evidence"])
    wet = next(k for k, v in query.payload["labels"].items() if v == "Wet")
    assert query.payload["priors"][wet]["yes"] == pytest.approx(0.2 * 0.9 + 0.8 * 0.1)
    assert not query.stale
    _json("bn", "set-cpt", "Rain", "--probs", "0.3,0.7")
    assert all(r.stale for r in ar.report_results(root=root))


def test_sd(sd_bathtub_root, monkeypatch) -> None:
    monkeypatch.chdir(sd_bathtub_root)
    assert _json("sd", "check")["result"]["ready"] is True
    assert {r["node"]: r["role"] for r in _json("sd", "roles")["result"]}["Water"] == "stock"
    assert _json("sd", "stocks")["result"][0]["initial_value"] == 100
    assert any(e["equation"] == "water * drain_rate" for e in _json("sd", "equations")["result"])
    assert _json("sd", "constants")["result"] and _json("sd", "tables")["result"] == []
    assert "commit_sha" in _json("sd", "set-constant", "Drain Rate", "0.2", "-u", "1/year")
    run = _json("sd", "simulate", "--final-time", "10", "--no-record")["result"]
    water = next(v for v in run["variables"] if v["variable"] == "Water")
    assert run["success"] and water["start"] == 100 and len(run["times"]) <= 60


def test_interpretation_sections(loop: Path) -> None:
    from latris.operations.project import update_selected_models

    update_selected_models(["cld"])
    made = _json("interpret", "initialise")["result"]["sections"]
    assert any(s["claims"] for s in made)
    listed = _json("interpret", "list")["result"]
    assert {s["section"] for s in listed} == {s["section"] for s in made}
    assert all(s["title"] for s in listed)
