"""The record stays honest: quotes are looked up, "against" isn't "checked", sources can be corrected, prose goes stale."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from latris.exporters import markdown
from latris.operations import build as build_ops
from latris.operations.handover import handover_check
from latris.operations.init import init_project
from latris.operations.project import update_selected_models
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import EvidenceLink, EvidenceLinkSet, ReferenceLibrary

SPEC = """
outcome: Departures
factors:
  - label: Workload
  - label: Burnout
  - label: Departures
links:
  - {from: Workload, to: Burnout, polarity: "+", sources: [smith2024]}
  - {from: Burnout, to: Departures, polarity: "+", sources: [lee2020], contradicts: [tuohy2015]}
  - {from: Departures, to: Workload, polarity: "+", confidence: by-definition}
sources:
  - key: smith2024
    title: Burnout among community volunteers
    url: https://example.org/smith
    extract: "Abstract: Longer rostered hours predicted emotional exhaustion among volunteers (r = 0.41)."
  - {key: lee2020, title: Why volunteers stay, url: https://example.org/lee}
  - {key: tuohy2015, title: Burnout and retention, url: https://example.org/tuohy}
  - {key: jones2019, title: Primary study, cited_via: lee2020}
"""

CHECK = ["evidence", "check", "Workload -> Burnout", "polarity", "smith2024", "supports", "-r", "Hours predict it."]


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    update_selected_models(["cld"], root=root)
    build_ops.build_from_spec(build_ops.load_spec(SPEC), root=root)
    monkeypatch.chdir(root)
    return root


def _links(root: Path) -> list[EvidenceLink]:
    return load_model(EvidenceLinkSet, ProjectPaths(root).evidence_links_yaml).entries


def _link(root: Path, key: str) -> EvidenceLink:
    return next(e for e in _links(root) if e.bibkey == key)


def _report(root: Path) -> str:
    return markdown.render(ProjectPaths(root), pack="review")


def _kinds(root: Path) -> dict[str, int]:
    return {i.kind: i.count for i in handover_check(root=root).items}


# ── Quotes are looked up ─────────────────────────────────────────────


def test_an_ai_paraphrase_is_refused(project: Path) -> None:
    result = CliRunner().invoke(app, [*CHECK, "--by", "ai", "--quote", "Working long hours burns volunteers out."])
    assert result.exit_code != 0
    assert "isn't in the text Latris holds" in result.output
    assert _link(project, "smith2024").support_verdict == "unverified"


def test_an_ai_supports_needs_a_quote(project: Path) -> None:
    result = CliRunner().invoke(app, [*CHECK, "--by", "ai"])
    assert result.exit_code != 0 and "needs --quote" in result.output


def test_a_copied_quote_is_found_despite_typography(project: Path) -> None:
    # Curly quotes, odd spacing, a different case and an ellipsis gap still match.
    quote = "longer  rostered hours predicted ... exhaustion among volunteers"
    result = CliRunner().invoke(app, [*CHECK, "--by", "ai", "--quote", quote])
    assert result.exit_code == 0, result.output
    link = _link(project, "smith2024")
    assert link.support_verdict == "supports" and link.quote_verified is True
    # Found in an abstract: the check rests on the abstract, not the full text.
    assert link.source_access == "abstract"
    assert "quote found in the stored text" in _report(project)
    assert "unfound_quotes" not in _kinds(project)


def test_a_persons_unfound_quote_is_recorded_and_flagged(project: Path) -> None:
    result = CliRunner().invoke(app, [*CHECK, "--quote", "Table 3 shows hours predict exhaustion strongly."])
    assert result.exit_code == 0, result.output
    link = _link(project, "smith2024")
    assert link.support_verdict == "supports" and link.quote_verified is False
    assert link.source_access == "abstract"  # not upgraded
    assert "quote not found in the stored text" in _report(project)
    assert _kinds(project)["unfound_quotes"] == 1


def test_a_legacy_quote_is_not_trusted(tmp_path: Path) -> None:
    legacy = EvidenceLink.model_validate({
        "target_id": "edge_x", "attribute": "polarity", "bibkey": "a",
        "support_verdict": "supports", "quote": "paraphrase", "source_access": "full_text_chunk",
    })
    assert legacy.quote_verified is None  # handover lists it with the unfound quotes


# ── "Against" is not "checked" ───────────────────────────────────────


def test_citing_against_is_not_checking(project: Path) -> None:
    link = _link(project, "tuohy2015")
    assert link.stance == "against" and link.support_verdict == "unverified" and link.is_against
    assert _kinds(project)["unchecked_citations"] == 3

    result = CliRunner().invoke(app, [
        "evidence", "check", "Burnout -> Departures", "polarity", "tuohy2015", "against", "-r", "It does argue so.",
    ])
    assert result.exit_code == 0, result.output
    link = _link(project, "tuohy2015")
    assert link.stance == "against" and link.support_verdict == "contradicts"
    report = _report(project)
    assert "## Contested links" in report and "checked: the source does argue against it" in report


def test_old_against_citations_are_migrated() -> None:
    attached, checked = EvidenceLinkSet.model_validate({"entries": [
        {"target_id": "e", "attribute": "polarity", "bibkey": "t", "support_verdict": "contradicts"},
        {"target_id": "e", "attribute": "polarity", "bibkey": "u", "support_verdict": "contradicts",
         "notes": "verdict unverified → contradicts (checked by a person): says the opposite"},
    ]}).entries
    assert attached.stance == "against" and attached.support_verdict == "unverified"
    assert checked.stance == "against" and checked.support_verdict == "contradicts"


# ── Correcting sources, as recorded changes ──────────────────────────


def test_ref_edit_and_remove_are_recorded(project: Path) -> None:
    run = CliRunner().invoke
    assert run(app, ["ref", "edit", "lee2020", "--doi", "https://doi.org/10.1234/lee.2020", "--year", "2020"]).exit_code == 0
    ref = next(r for r in load_model(ReferenceLibrary, ProjectPaths(project).references_yaml).entries
               if r.bibkey == "lee2020")
    assert ref.doi == "10.1234/lee.2020" and ref.year == 2020
    assert git.recent_commits(project, 1)[0]["subject"] == 'Updated reference "lee2020": year, doi'

    bad = run(app, ["ref", "edit", "lee2020", "--doi", "not a doi"])
    assert bad.exit_code != 0 and "isn't a DOI" in bad.output

    # Cited, and another source was read in it: refused until both are dealt with.
    refused = run(app, ["ref", "remove", "lee2020"])
    assert refused.exit_code != 0 and "jones2019" in refused.output
    assert run(app, ["ref", "edit", "jones2019", "--cited-via", ""]).exit_code == 0
    refused = run(app, ["ref", "remove", "lee2020"])
    assert refused.exit_code != 0 and "--with-citations" in refused.output
    assert run(app, ["ref", "remove", "lee2020", "--with-citations", "-r", "Couldn't find it"]).exit_code == 0
    assert all(e.bibkey != "lee2020" for e in _links(project))
    assert git.recent_commits(project, 1)[0]["subject"] == 'Removed reference "lee2020" and its 1 citation(s)'


def test_evidence_remove_is_recorded(project: Path) -> None:
    result = CliRunner().invoke(app, ["evidence", "remove", "Burnout -> Departures", "polarity", "tuohy2015"])
    assert result.exit_code == 0, result.output
    assert all(e.bibkey != "tuohy2015" for e in _links(project))
    assert git.recent_commits(project, 1)[0]["subject"].startswith('Detached evidence "tuohy2015"')


def test_second_hand_sources_say_so(project: Path) -> None:
    report = markdown.render(ProjectPaths(project), pack="client")
    assert "Read as cited in *Why volunteers stay*, not first-hand." in report
    with pytest.raises(ValueError) as bad:
        build_ops.build_from_spec(build_ops.load_spec(
            "sources:\n  - {key: a, title: A, cited_via: nowhere}\n  - {key: b, title: B, doi: '10.x'}\n"
        ), root=project)
    assert "cited_via 'nowhere'" in str(bad.value) and "isn't a DOI" in str(bad.value)


def test_sources_with_nothing_read_are_flagged(project: Path) -> None:
    kinds = _kinds(project)
    assert kinds["unread_sources"] == 2  # lee2020 and tuohy2015; smith2024 has its abstract


# ── Prose goes stale ─────────────────────────────────────────────────


def test_prose_goes_stale_when_the_model_changes(project: Path) -> None:
    run = CliRunner().invoke
    assert run(app, ["interpret", "initialise"]).exit_code == 0
    assert run(app, ["interpret", "set-prose", "structural_summary", "Three factors in a chain.", "--by", "ai"]).exit_code == 0
    assert "stale_prose" not in _kinds(project)

    assert run(app, ["node", "add", "Recognition"]).exit_code == 0
    assert run(app, ["edge", "add", "Recognition", "Departures"]).exit_code == 0
    assert _kinds(project)["stale_prose"] == 1
    assert "Out of date: the model has changed" in _report(project)

    out = run(app, ["interpret", "refresh-claims"]).output
    assert "out of date" in out and "structural_summary" in out
