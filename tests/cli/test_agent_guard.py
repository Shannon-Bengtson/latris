"""An AI agent driving the CLI is recorded as one, and records a person's judgement only on their say-so."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import build as build_ops
from latris.operations.init import init_project
from latris.operations.project import update_selected_models
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import EvidenceLinkSet, SignoffLog, Substrate

runner = CliRunner()

SPEC = """
factors: [{label: Workload}, {label: Burnout}]
links:
  - {from: Workload, to: Burnout, polarity: "+", sources: [smith2024]}
sources:
  - {key: smith2024, title: Burnout among volunteers, url: "https://example.org/b",
     extract: "Longer hours were followed by burnout in most crews."}
"""


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    update_selected_models(["cld"], root=root)
    build_ops.build_from_spec(build_ops.load_spec(SPEC), root=root)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def as_agent(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")


def _last_message(root: Path) -> str:
    return git.run_git(["log", "-1", "--format=%B"], cwd=root).stdout


def test_person_is_unchanged(project: Path) -> None:
    result = runner.invoke(app, ["node", "add", "Morale"])
    assert result.exit_code == 0, result.output
    assert "Recorded-by-agent" not in _last_message(project)
    assert runner.invoke(app, ["mature", "approve", "Morale"]).exit_code == 0


def test_agent_work_is_recorded_as_ai(project: Path, as_agent) -> None:
    assert runner.invoke(app, ["node", "add", "Morale"]).exit_code == 0
    node = next(e for e in load_model(Substrate, ProjectPaths(project).conceptual_yaml).entities if e.label == "Morale")
    assert node.origin == "ai-proposed"
    message = _last_message(project)
    assert "Recorded-by-agent: claude-code" in message
    assert "Provenance: ai-proposed" in message


@pytest.mark.parametrize(
    "args",
    [
        ["mature", "approve", "Workload"],
        ["mature", "review", "Workload"],
        ["signoff", "record", "--role", "Lead", "--scope", "Model"],
    ],
)
def test_agent_needs_the_persons_say_so_for_judgements(project: Path, as_agent, args: list[str]) -> None:
    refused = runner.invoke(app, args)
    assert refused.exit_code != 0
    assert "--confirmed-by-person" in refused.output

    allowed = runner.invoke(app, [*args, "--confirmed-by-person"])
    assert allowed.exit_code == 0, allowed.output
    assert "(on the person's instruction)" in _last_message(project)


def test_agent_approval_for_person_keeps_person_as_reviewer(project: Path, as_agent, git_identity) -> None:
    assert runner.invoke(app, ["mature", "approve", "Workload", "--confirmed-by-person"]).exit_code == 0
    signoff = load_model(SignoffLog, ProjectPaths(project).signoffs_yaml).entries[-1]
    assert signoff.reviewer.name == git_identity[0]
    assert "Provenance: human-authored" in _last_message(project)


def test_agent_evidence_check_defaults_to_ai(project: Path, as_agent) -> None:
    args = ["evidence", "check", "Workload -> Burnout", "polarity", "smith2024", "supports",
            "--rationale", "Hours precede burnout.", "--quote", "Longer hours were followed by burnout"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    link = load_model(EvidenceLinkSet, ProjectPaths(project).evidence_links_yaml).entries[0]
    assert link.support_verdict == "supports"
    assert "(checked by an AI)" in (link.notes or "")

    refused = runner.invoke(app, [*args, "--by", "human"])
    assert refused.exit_code != 0 and "--confirmed-by-person" in refused.output


def test_agent_detection_can_be_turned_off(project: Path, as_agent, monkeypatch) -> None:
    monkeypatch.setenv("LATRIS_AGENT", "none")
    assert runner.invoke(app, ["mature", "approve", "Workload"]).exit_code == 0
    assert "Recorded-by-agent" not in _last_message(project)


def test_ai_agent_convention_names_the_agent(project: Path, monkeypatch) -> None:
    monkeypatch.setenv("AI_AGENT", "some-agent")
    assert runner.invoke(app, ["node", "add", "Morale"]).exit_code == 0
    assert "Recorded-by-agent: some-agent" in _last_message(project)


def test_agent_resolving_a_challenge_needs_the_persons_say_so(project: Path, as_agent) -> None:
    from latris.operations.challenges import open_challenge

    challenge, _ = open_challenge("Workload", "Is it hours or the kind of work?", root=project)
    args = ["challenge", "resolve", challenge.id, "--state", ops_state(), "--rationale", "Hours, per the survey."]
    assert runner.invoke(app, args).exit_code != 0
    assert runner.invoke(app, [*args, "--confirmed-by-person"]).exit_code == 0


def ops_state() -> str:
    from latris.operations.challenges import TERMINAL_STATES

    return next(iter(TERMINAL_STATES))
