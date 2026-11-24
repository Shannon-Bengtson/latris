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
    contradicts: [tuohy2015]
sources:
  - key: smith2024
    title: Burnout among community volunteers
    authors: ["Smith, Jane"]
    year: 2024
  - key: tuohy2015
    title: Workload and retention revisited
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
    assert (result.factors, len(result.links), result.sources, result.citations) == (3, 3, 2, 2)

    paths = ProjectPaths(project)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    assert len(substrate.edges) == 3
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    assert evidence.entries[0].target_id == result.links[0]["id"]
    assert evidence.entries[0].attribute == "polarity"
    against = [e for e in evidence.entries if e.is_against]
    assert [(e.bibkey, e.target_id) for e in against] == [("tuohy2015", result.links[2]["id"])]
    # Citing a source as against a link is not checking it.
    assert against[0].stance == "against" and against[0].support_verdict == "unverified"
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
    assert resp.json()["result"]["citations"] == 2


def test_every_problem_is_listed_in_order(project: Path) -> None:
    bad = """
outcome: Nowhere
factors:
  - label: Workload
  - label: Workload
  - label: Burnout
links:
  - {from: Workload, to: Workload, polarity: "+"}
  - {from: Workload, to: Burnout, polarity: "+", sources: [nobody2020]}
  - {from: Workload, to: Burnout, polarity: "+"}
  - {from: Burnout, to: Morale, polarity: "-"}
sources:
  - {key: long2020, title: Too long, url: "https://example.org/a", extract: "%s"}
  - {key: bare2021, title: No address, extract: A passage.}
  - {key: self2022, title: Cites itself, cited_via: self2022}
assumptions:
  - {text: Hours are comparable., target: Recognition}
findings:
  - {statement: Burnout follows workload., category: dynamics, targets: ["Burnout -> Workload"]}
interpretation:
  - {section: no_such_section, prose: Words.}
""" % ("x" * 2001)
    with pytest.raises(ValueError) as exc:
        build_ops.build_from_spec(build_ops.load_spec(bad), root=project)
    lines = str(exc.value).splitlines()
    assert lines[:12] == [
        "the spec has problems, nothing was changed:",
        "- source 'long2020': extract is 2001 characters (limit 2000); keep the passage that bears on the claim",
        "- source 'bare2021': an extract needs extract_url (or the source's url or doi)",
        "- source 'self2022': cited_via 'self2022' isn't another source",
        "- factor listed twice: Workload",
        "- link 1: a factor can't link to itself",
        "- link 4: no factor named 'Morale'",
        "- link 3: Workload -> Burnout (causal) is already a link",
        "- link 2: no source with key 'nobody2020' (add it under sources)",
        "- outcome: no factor named 'Nowhere'",
        "- assumption 1: no factor named 'Recognition'",
        "- finding 1: no link 'Burnout -> Workload'",
    ]
    assert lines[12].startswith("- interpretation: no section 'no_such_section' (one of: answer_to_question, ")
    assert len(lines) == 13


def test_building_the_same_spec_again_reusing_adds_nothing(project: Path) -> None:
    spec = build_ops.load_spec(SPEC)
    build_ops.build_from_spec(spec, root=project)
    paths = ProjectPaths(project)
    before = (paths.conceptual_yaml.read_text(encoding="utf-8"), paths.evidence_links_yaml.read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="factor already in the project"):
        build_ops.build_from_spec(spec, root=project)
    result = build_ops.build_from_spec(spec, existing="reuse", root=project)

    assert (result.reused_factors, result.reused_links, result.reused_sources) == (3, 3, 2)
    assert (result.factors, result.links, result.sources, result.citations) == (0, [], 0, 0)
    after = (paths.conceptual_yaml.read_text(encoding="utf-8"), paths.evidence_links_yaml.read_text(encoding="utf-8"))
    assert after == before  # the links keep their values and each source is cited once
