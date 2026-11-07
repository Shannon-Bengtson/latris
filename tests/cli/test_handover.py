"""Getting a model ready to hand over: checking sources, the handover list, and the docs that ship."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import build as build_ops
from latris.operations.handover import handover_check
from latris.operations.init import init_project
from latris.operations.project import update_selected_models
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import DecisionLog, EvidenceLinkSet

SPEC = """
outcome: Departures
factors:
  - label: Workload
  - label: Burnout
  - label: Departures
links:
  - {from: Workload, to: Burnout, polarity: "+", sources: [smith2024]}
  - {from: Burnout, to: Departures, polarity: "+"}
  - {from: Departures, to: Workload, polarity: "+", confidence: by-definition}
sources:
  - {key: smith2024, title: Burnout among community volunteers}
findings:
  - {statement: Workload drives departures through burnout., category: dynamics}
decisions:
  - {statement: Left out paid staff., rationale: The program has none., target: Workload}
"""


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    update_selected_models(["cld"], root=root)
    build_ops.build_from_spec(build_ops.load_spec(SPEC), root=root)
    monkeypatch.chdir(root)
    return root


def _kinds(root: Path) -> dict[str, int]:
    return {i.kind: i.count for i in handover_check(root=root).items}


def test_handover_lists_what_is_left(project: Path) -> None:
    kinds = _kinds(project)
    # The by-definition link needs no source; Burnout -> Departures does.
    assert kinds["unsourced_links"] == 1
    assert kinds["unchecked_citations"] == 1
    assert kinds["unapproved_findings"] == 1
    assert kinds["missing_prose"] == 1

    result = CliRunner().invoke(app, ["check", "handover"])
    assert result.exit_code == 1
    assert "Ready to hand over: no" in result.output and "Burnout → Departures" in result.output
    data = json.loads(CliRunner().invoke(app, ["--json", "check", "handover"]).output)
    assert data["result"]["ready"] is False


def test_a_person_can_check_a_citation_against_its_source(project: Path) -> None:
    result = CliRunner().invoke(app, [
        "evidence", "check", "Workload -> Burnout", "polarity", "smith2024", "supports",
        "--rationale", "Table 3: hours predict exhaustion.",
    ])
    assert result.exit_code == 0, result.output
    link = load_model(EvidenceLinkSet, ProjectPaths(project).evidence_links_yaml).entries[0]
    assert link.support_verdict == "supports"
    assert link.verified_by == "human"  # who attached it is unchanged
    assert "(checked by a person)" in (link.notes or "")
    assert "unchecked_citations" not in _kinds(project)

    bad = CliRunner().invoke(app, ["evidence", "check", "Workload -> Burnout", "polarity", "smith2024", "maybe",
                                   "-r", "x"])
    assert bad.exit_code == 2 and "supports" in bad.output


def test_links_resolve_by_name(project: Path) -> None:
    ok = CliRunner().invoke(app, ["attr", "set", "Burnout → Departures", "confidence", "low"])
    assert ok.exit_code == 0, ok.output
    missing = CliRunner().invoke(app, ["attr", "set", "Departures -> Burnout", "confidence", "low"])
    assert missing.exit_code != 0 and "no link from" in missing.output


def test_decisions_come_in_from_the_spec_and_travel_in_the_link(project: Path) -> None:
    from latris.operations.share_link import export_spec

    entries = load_model(DecisionLog, ProjectPaths(project).decisions_yaml).entries
    assert [d.statement for d in entries] == ["Left out paid staff."]
    _, spec = export_spec(root=project)
    assert spec.decisions[0].target == "Workload"


def test_spec_rejects_unknown_confidence_and_names_the_choices(project: Path) -> None:
    with pytest.raises(ValueError) as err:
        build_ops.load_spec('links:\n  - {from: A, to: B, confidence: moderate}\n')
    assert "by-definition" in str(err.value)


def test_docs_ship_with_the_package() -> None:
    result = CliRunner().invoke(app, ["docs"])
    assert result.exit_code == 0
    assert result.output.startswith("## For AI agents") and "latris build --spec" in result.output
    assert "# Latris" in CliRunner().invoke(app, ["docs", "llms"]).output
    assert CliRunner().invoke(app, ["docs", "nonsense"]).exit_code == 2


def test_init_speaks_json(tmp_path: Path, git_identity, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["--json", "init", "p", "-q", "Why?"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["result"]["question"] == "Why?"


def test_initialise_fills_claims_and_ai_findings_say_so(project: Path, monkeypatch) -> None:
    from latris.operations.findings import record_new_finding
    from latris.operations.interpret import initialise_sections

    store, _, _ = initialise_sections(root=project)
    assert store.sections and all(s.generation_state == "claims_only" for s in store.sections)
    assert any(s.claims for s in store.sections)

    monkeypatch.setenv("LATRIS_DEFAULT_ORIGIN", "ai-proposed")
    finding, _ = record_new_finding("Burnout matters.", "dynamics", "cld", root=project)
    assert (finding.origin, finding.source_type) == ("ai-proposed", "ai-interaction")
