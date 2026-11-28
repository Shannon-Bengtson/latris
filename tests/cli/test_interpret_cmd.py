"""`latris interpret`: sections, claims and prose — flags, output modes and error paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.ai.proposals import InterpretProseResult
from latris.cli.app import app
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.operations.interpret import load_interpretation
from latris.operations.project import update_selected_models

runner = CliRunner()


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


def _prose(text: str = "Generated prose.") -> None:
    MockAdapter.shared().register_default(
        response_cls=InterpretProseResult,
        result=ChatResult(
            parsed=InterpretProseResult(prose=text), raw="(mock)", model_id="mock-model", cost_usd=0.0012
        ),
    )


@pytest.fixture
def empty(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "empty"
    init_project(root, statement="Why?")
    update_selected_models(["cld"], root=root)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def loop(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "loop"
    init_project(root, statement="Why are volunteers leaving?")
    update_selected_models(["cld"], root=root)
    w, _ = node_ops.add_node("Workload", kind="variable", root=root)
    b, _ = node_ops.add_node("Burnout", kind="state", root=root)
    for src, dst in ((w, b), (b, w)):
        e, _ = edge_ops.add_edge(src.id, dst.id, kind="causal", root=root)
        view_attr_ops.set_view_attribute(e.id, "cld", "polarity", "+", root=root)
    monkeypatch.chdir(root)
    assert runner.invoke(app, ["interpret", "initialise"]).exit_code == 0
    return root


def _first(root: Path):
    return load_interpretation(root=root).sections[0]


def test_nothing_initialised(empty: Path) -> None:
    out = runner.invoke(app, ["interpret", "list"]).output
    assert "no sections" in out
    result = runner.invoke(app, ["interpret", "show", "answer_to_question"])
    assert result.exit_code == 2
    assert "run `latris interpret initialise` first" in result.output
    result = runner.invoke(app, ["interpret", "generate-all"])
    assert result.exit_code == 0
    assert "no sections to generate" in result.output


def test_initialise_reports_skipped_types(empty: Path) -> None:
    result = runner.invoke(app, ["interpret", "initialise"])
    assert result.exit_code == 0, result.output
    assert "skipped" in result.output
    result = runner.invoke(app, ["--json", "interpret", "initialise"])
    payload = json.loads(result.output)["result"]
    assert payload["skipped"] and payload["skipped"][0]["model_type"] == "cld"


def test_initialise_and_list_as_json(loop: Path) -> None:
    result = runner.invoke(app, ["--json", "interpret", "initialise"])
    sections = json.loads(result.output)["result"]["sections"]
    assert sections and {"section", "title", "claims", "prose", "state", "stale"} <= set(sections[0])
    listed = json.loads(runner.invoke(app, ["--json", "interpret", "list"]).output)["result"]
    assert len(listed) == len(sections)
    out = runner.invoke(app, ["interpret", "list"]).output
    assert "claims=" in out and "prose=0c" in out


def test_show_and_set_prose(loop: Path) -> None:
    sec = _first(loop)
    out = runner.invoke(app, ["interpret", "show", sec.id]).output
    assert "Claims" in out and "Prose" in out and "(empty)" in out

    result = runner.invoke(app, ["interpret", "set-prose", sec.id, "My words.", "--by", "robot"])
    assert result.exit_code == 2
    assert "--by must be 'human' or 'ai'" in result.output

    result = runner.invoke(app, ["interpret", "set-prose", sec.id, "My words."])
    assert result.exit_code == 0, result.output
    assert "wrote" in result.output
    shown = json.loads(runner.invoke(app, ["--json", "interpret", "show", sec.id]).output)["result"]
    assert shown["prose"] == "My words."


def test_set_prose_by_human_under_an_agent(loop: Path, monkeypatch) -> None:
    sec = _first(loop)
    monkeypatch.setenv("LATRIS_AGENT", "test-agent")
    result = runner.invoke(app, ["interpret", "set-prose", sec.id, "x", "--by", "human"])
    assert result.exit_code == 2
    assert "--confirmed-by-person" in result.output
    # Left unset, an agent's prose is recorded as AI-written and needs no confirmation.
    assert runner.invoke(app, ["interpret", "set-prose", sec.id, "x"]).exit_code == 0


def test_show_unknown_section(loop: Path) -> None:
    result = runner.invoke(app, ["interpret", "show", "no_such_section"])
    assert result.exit_code == 2
    assert "no interpretation section" in result.output


def test_refresh_claims_all_and_one(loop: Path) -> None:
    sec = _first(loop)
    runner.invoke(app, ["interpret", "set-prose", sec.id, "Old prose."])
    # Change the model so the claims move under the prose.
    node_ops.add_node("Recognition", kind="variable", root=loop)
    result = runner.invoke(app, ["interpret", "refresh-claims"])
    assert result.exit_code == 0, result.output
    assert "refreshed" in result.output

    result = runner.invoke(app, ["interpret", "refresh-claims", "--section", sec.id])
    assert result.exit_code == 0, result.output
    assert f"refreshed {sec.section_type}" in result.output


def test_stale_prose_is_flagged(loop: Path) -> None:
    from latris.operations.interpret import update_prose

    sec = _first(loop)
    update_prose(sec.id, "Written against old claims.", source="human-edit", root=loop)
    store = load_interpretation(root=loop)
    target = next(s for s in store.sections if s.id == sec.id)
    if not target.claims:
        pytest.skip("this section has no claims to change")
    # Make the stored claims differ from those the prose was written against.
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import dump_model

    target.claims = [*target.claims, "A new claim."]
    dump_model(store, ProjectPaths(loop).interpretation_yaml)
    assert "out of date" in runner.invoke(app, ["interpret", "show", sec.id]).output
    assert "(out of date)" in runner.invoke(app, ["interpret", "list"]).output


def test_generate_prose_and_all(loop: Path) -> None:
    _prose("AI wrote this.")
    sec = _first(loop)
    result = runner.invoke(app, ["interpret", "generate-prose", sec.id, "--yes"])
    assert result.exit_code == 0, result.output
    assert f"generated {sec.section_type}" in result.output
    assert "cost $0.0012" in result.output
    assert load_interpretation(root=loop).sections[0].prose == "AI wrote this."

    result = runner.invoke(app, ["interpret", "generate-all"])
    assert result.exit_code == 0, result.output
    n = len(load_interpretation(root=loop).sections)
    assert f"{n}/{n} sections" in result.output


def test_generate_all_reports_failures(loop: Path) -> None:
    # No mock response registered: every section's call fails, and the command says so.
    result = runner.invoke(app, ["interpret", "generate-all"])
    assert result.exit_code == 1
    assert "0/" in result.output
