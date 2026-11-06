"""Writing board-ready interpretation prose without an AI key, and finding the report options."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.exporters import markdown as md_exporter
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.operations.project import update_selected_models
from latris.repo.layout import ProjectPaths

runner = CliRunner()


def _json(args: list[str]) -> tuple[int, dict]:
    result = runner.invoke(app, ["--json", *args])
    return result.exit_code, json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture
def loop_project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    """A CLD with one reinforcing loop — enough for interpretation sections."""
    root = tmp_path / "vol"
    init_project(root, statement="Why are volunteers leaving?")
    update_selected_models(["cld"], root=root)
    w, _ = node_ops.add_node("Workload", kind="variable", root=root)
    b, _ = node_ops.add_node("Burnout", kind="state", root=root)
    d, _ = node_ops.add_node("Departures", kind="variable", root=root)
    for src, dst in ((w, b), (b, d), (d, w)):
        e, _ = edge_ops.add_edge(src.id, dst.id, kind="causal", root=root)
        view_attr_ops.set_view_attribute(e.id, "cld", "polarity", "+", root=root)
    monkeypatch.chdir(root)
    return root


def test_agent_writes_interpretation_without_a_key(loop_project: Path) -> None:
    init = runner.invoke(app, ["interpret", "initialise"])
    assert init.exit_code == 0 and "initialised 10" in init.stdout, init.stdout

    code, payload = _json(["interpret", "show", "answer_to_question"])
    shown = payload["result"]
    assert code == 0
    assert shown["section_type"] == "answer_to_question"
    assert isinstance(shown["claims"], list)

    code, wrote = _json(["interpret", "set-prose", "answer_to_question",
                         "Departures feed back into workload, so losses accelerate.", "--by", "ai"])
    assert code == 0
    assert wrote["result"]["generation_state"] == "generated"

    out = md_exporter.render(ProjectPaths(loop_project), pack="client", ai=False)
    assert "Departures feed back into workload, so losses accelerate." in out


def test_unknown_section_lists_the_options(loop_project: Path) -> None:
    runner.invoke(app, ["interpret", "initialise"])
    code, err = _json(["interpret", "show", "nonsense"])
    assert code == 2
    assert "answer_to_question" in err["error"]


def test_set_prose_before_initialise_explains(loop_project: Path) -> None:
    code, err = _json(["interpret", "set-prose", "answer_to_question", "x"])
    assert code == 2
    assert "interpret initialise" in err["error"]


def test_capabilities_describe_the_reports() -> None:
    result = runner.invoke(app, ["--json", "capabilities"])  # global --json works too
    assert result.exit_code == 0
    manifest = json.loads(result.stdout)
    reports = manifest["reports"]
    packs = {p["name"]: p for p in reports["packs"]}
    assert set(packs) == {"client", "audit", "review", "workshop", "publication"}
    assert all(p["audience"] and p["purpose"] for p in packs.values())
    assert "interpret set-prose" in reports["board_ready_prose"]
    assert "Word report" in reports["app_formats"]["formats"]

    text = runner.invoke(app, ["capabilities"]).stdout
    assert "Reports" in text and "client: for people outside the modelling work" in text
