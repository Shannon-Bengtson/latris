"""``latris checkpoint`` and the checkpoint an agent sees in ``build`` / ``check handover`` output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import PersonInputLog

runner = CliRunner()

SPEC = """
factors: [{label: Workload}, {label: Burnout}, {label: Volunteers}]
links:
  - {from: Workload, to: Burnout, polarity: "+"}
  - {from: Burnout, to: Volunteers, polarity: "-"}
  - {from: Volunteers, to: Workload, polarity: "-"}
"""


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", "test-agent")


def test_show_lists_states_and_the_open_one(project: Path) -> None:
    out = runner.invoke(app, ["checkpoint", "show"])
    assert out.exit_code == 0, out.output
    assert "framing" in out.output and "open — ask now" in out.output
    data = json.loads(runner.invoke(app, ["--json", "checkpoint", "show"]).output)["result"]
    assert data["pace"] == "ask" and data["open"]["id"] == "framing"
    assert [c["id"] for c in data["checkpoints"]] == ["framing", "structure", "values", "surprise", "audience"]


def test_record_skip_and_pace(project: Path, agent) -> None:
    out = runner.invoke(app, ["checkpoint", "record", "framing", "--answers", "It's for the board; I expect burnout."])
    assert out.exit_code == 0, out.output
    out = runner.invoke(app, ["checkpoint", "skip", "structure", "--reason", "The person said carry on."])
    assert out.exit_code == 0, out.output
    out = runner.invoke(app, ["checkpoint", "pace", "just-build"])
    assert out.exit_code == 0, out.output
    log = load_model(PersonInputLog, ProjectPaths(project).person_input_yaml)
    assert log.pace == "just_build"
    assert [(e.checkpoint, e.outcome, e.relayed_by) for e in log.entries] == [
        ("framing", "answered", "test-agent"), ("structure", "skipped", "test-agent")]
    assert runner.invoke(app, ["checkpoint", "pace", "sometimes"]).exit_code != 0
    assert runner.invoke(app, ["checkpoint", "record", "vibes", "--answers", "x"]).exit_code != 0


def test_agent_sees_the_checkpoint_after_build(project: Path, agent) -> None:
    (project / "spec.yaml").write_text(SPEC, encoding="utf-8")
    out = runner.invoke(app, ["build", "--spec", "spec.yaml"])
    assert out.exit_code == 0, out.output
    assert "Checkpoint: framing" in out.output  # nothing framed yet: ask first
    runner.invoke(app, ["checkpoint", "skip", "framing", "--reason", "The request said enough."])
    data = json.loads(runner.invoke(app, ["--json", "check", "handover"]).output)["result"]
    assert data["checkpoint"]["id"] == "structure"
    assert any("Workload" in q for q in data["checkpoint"]["questions"])


def test_a_person_at_a_terminal_is_not_nagged(project: Path) -> None:
    (project / "spec.yaml").write_text(SPEC, encoding="utf-8")
    out = runner.invoke(app, ["build", "--spec", "spec.yaml"])
    assert out.exit_code == 0, out.output
    assert "Checkpoint" not in out.output
