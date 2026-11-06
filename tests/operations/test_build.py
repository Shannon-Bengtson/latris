"""`latris build --spec`: a whole model from one file, as one commit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import build as build_ops
from latris.operations.init import init_project
from latris.operations.project import update_selected_models
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import EvidenceLinkSet, Substrate
from latris.schema.roles import RoleSet

SPEC = """
outcome: Volunteer departures
factors:
  - label: Workload per volunteer
    description: Hours each active volunteer covers.
  - label: Volunteer burnout
  - label: Volunteer departures
links:
  - from: Workload per volunteer
    to: Volunteer burnout
    polarity: "+"
    reason: More hours per person, more exhaustion.
    confidence: high
    sources: [smith2024]
  - from: Volunteer burnout
    to: Volunteer departures
    polarity: "+"
    reason: Exhausted volunteers leave.
  - from: Volunteer departures
    to: Workload per volunteer
    polarity: "+"
    reason: Fewer people share the same work.
sources:
  - key: smith2024
    title: Burnout among community volunteers
    authors: ["Smith, Jane"]
    year: 2024
assumptions:
  - Hours are comparable across programs.
questions:
  - Does recognition matter independently of workload?
"""


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    update_selected_models(["cld"], root=root)
    return root


def _commits(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


def test_builds_everything_in_one_commit(project: Path) -> None:
    before = _commits(project)
    result = build_ops.build_from_spec(build_ops.load_spec(SPEC), root=project)
    assert _commits(project) == before + 1
    assert (result.factors, len(result.links), result.sources, result.citations) == (3, 3, 1, 1)

    paths = ProjectPaths(project)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    assert len(substrate.edges) == 3
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    assert evidence.entries[0].target_id == result.links[0]["id"]
    assert evidence.entries[0].attribute == "polarity"
    roles = load_model(RoleSet, paths.role_path("cld"))
    departures = next(e.id for e in substrate.entities if e.label == "Volunteer departures")
    assert [(r.target_id, r.value) for r in roles.entries] == [(departures, "outcome")]


def test_a_bad_spec_changes_nothing(project: Path) -> None:
    bad = SPEC.replace("to: Volunteer burnout", "to: Volunter burnout").replace("[smith2024]", "[nobody2020]")
    before = _commits(project)
    with pytest.raises(ValueError) as exc:
        build_ops.build_from_spec(build_ops.load_spec(bad), root=project)
    message = str(exc.value)
    assert "no factor named 'Volunter burnout'" in message
    assert "no source with key 'nobody2020'" in message
    assert _commits(project) == before
    assert not load_model(Substrate, ProjectPaths(project).conceptual_yaml).entities


def test_cli_reads_json_from_stdin(project: Path, monkeypatch) -> None:
    import yaml as pyyaml

    monkeypatch.chdir(project)
    spec_json = json.dumps(pyyaml.safe_load(SPEC))
    result = CliRunner().invoke(app, ["--json", "build", "--spec", "-"], input=spec_json)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["result"]["factors"] == 3
    assert payload["commit_sha"]

    again = CliRunner().invoke(app, ["build", "--spec", "-"], input=spec_json)
    assert again.exit_code == 2
    assert "already in the project" in again.output


def test_route(project: Path) -> None:
    import yaml as pyyaml

    from latris.server.app import create_app

    client = TestClient(create_app(project_root=project))
    resp = client.post("/api/build", json={"spec": pyyaml.safe_load(SPEC), "verified_by": "ai"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"]["citations"] == 1
