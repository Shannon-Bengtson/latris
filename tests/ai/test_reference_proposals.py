"""Reference-management proposals: what their ``apply()`` writes to the project.

``CrossReferenceCheckResult`` and ``EvidenceGapsScanResult`` are hybrid: the prose
renders into the report, and only their suggested evidence links (and, for the
gap scan, the gaps as open questions) are committed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.proposals import (
    CitationSuggestion,
    CrossReferenceCheckResult,
    EvidenceGap,
    EvidenceGapsScanResult,
    EvidenceLinkSuggestion,
    ExpandBibliographyProposal,
    UncitedElement,
)
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.references import add_reference, list_references
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import EvidenceLinkSet, QuestionLog


@pytest.fixture
def paths(tmp_path: Path, git_identity) -> ProjectPaths:
    root = tmp_path / "proj"
    init_project(root, statement="Why is the lagoon turbid?")
    return ProjectPaths(root)


def _links(paths: ProjectPaths) -> list:
    return load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries


def _questions(paths: ProjectPaths) -> list[str]:
    return [q.question for q in load_model(QuestionLog, paths.questions_yaml).entries]


# ── ExpandBibliographyProposal ───────────────────────────────────────────────


def test_expand_bibliography_keeps_metadata_and_skips_repeats_within_proposal(paths) -> None:
    proposal = ExpandBibliographyProposal(
        new_references=[
            CitationSuggestion(
                bibkey="smith2020", title="Sediment loads", authors=["Smith, J."], year=2020,
                doi="10.1000/xyz", url="https://example.org/s",
            ),
            CitationSuggestion(bibkey="smith2020", title="Duplicate in the same batch"),
        ]
    )
    assert proposal.apply(paths) == ["smith2020"]

    [ref] = list_references(paths.root)
    assert (ref.title, ref.authors, ref.year, ref.doi) == (
        "Sediment loads", ["Smith, J."], 2020, "10.1000/xyz",
    )


def test_expand_bibliography_empty_is_a_no_op(paths) -> None:
    assert ExpandBibliographyProposal().apply(paths) == []
    assert list_references(paths.root) == []


# ── CrossReferenceCheckResult ────────────────────────────────────────────────


def test_cross_reference_prose_only_writes_nothing(paths) -> None:
    result = CrossReferenceCheckResult(
        uncited_elements=[UncitedElement(element_id="n1", label="Turbidity")],
        unused_references=["orphan2019"],
        coverage_summary="Half the links are uncited.",
    )
    assert result.apply(paths) == []
    assert _links(paths) == []


def test_cross_reference_attaches_suggested_links_as_ai_verified(paths) -> None:
    node, _ = node_ops.add_node("Turbidity", root=paths.root)
    add_reference("jones2018", "Turbidity drivers", root=paths.root)
    result = CrossReferenceCheckResult(
        suggested_links=[
            EvidenceLinkSuggestion(target_id=node.id, bibkey="jones2018", rationale="Measures it directly."),
            EvidenceLinkSuggestion(target_id=node.id, attribute="description", bibkey="jones2018"),
        ]
    )
    created = result.apply(paths)

    assert created == [
        f"evidence:jones2018->{node.id}/existence",
        f"evidence:jones2018->{node.id}/description",
    ]
    links = _links(paths)
    assert [(lk.target_id, lk.attribute, lk.verified_by) for lk in links] == [
        (node.id, "existence", "ai"),
        (node.id, "description", "ai"),
    ]
    assert links[0].notes == "Measures it directly."
    assert links[1].notes is None  # an empty rationale is not stored as a note


def test_cross_reference_refuses_a_reference_not_in_the_library(paths) -> None:
    node, _ = node_ops.add_node("Turbidity", root=paths.root)
    result = CrossReferenceCheckResult(
        suggested_links=[EvidenceLinkSuggestion(target_id=node.id, bibkey="invented2024")]
    )
    # The safety rail: an AI-suggested link can only point at a real library entry.
    with pytest.raises(ValueError, match="unknown reference"):
        result.apply(paths)
    assert _links(paths) == []


# ── EvidenceGapsScanResult ───────────────────────────────────────────────────


def _gap(description: str, *, severity: str = "medium", action: str = "") -> EvidenceGap:
    return EvidenceGap(
        section_type="evidence_gaps", gap_description=description, severity=severity, suggested_action=action
    )


def test_gap_scan_logs_each_gap_as_an_open_question(paths) -> None:
    result = EvidenceGapsScanResult(
        gaps=[
            _gap("No field data on sediment.", severity="high", action="search for monitoring studies"),
            _gap("Rainfall link is assumed.", severity="low"),
        ],
        summary="Thin evidence.",
    )
    created = result.apply(paths)

    assert len(created) == 2 and all(c.startswith("question_") for c in created)
    assert _questions(paths) == [
        "[evidence/high] No field data on sediment. — Suggested: search for monitoring studies",
        "[evidence/low] Rainfall link is assumed.",
    ]


def test_gap_scan_can_skip_questions_and_still_attach_links(paths) -> None:
    node, _ = node_ops.add_node("Sediment", root=paths.root)
    add_reference("lee2021", "Sediment budgets", root=paths.root)
    result = EvidenceGapsScanResult(
        gaps=[_gap("Weak support.")],
        record_as_questions=False,
        suggested_evidence_links=[
            EvidenceLinkSuggestion(target_id=node.id, bibkey="lee2021", rationale="Budget study.")
        ],
    )
    assert result.apply(paths) == [f"evidence:lee2021->{node.id}/existence"]
    assert _questions(paths) == []
    [link] = _links(paths)
    assert (link.target_id, link.bibkey, link.verified_by, link.notes) == (
        node.id, "lee2021", "ai", "Budget study.",
    )


def test_gap_scan_questions_and_links_together(paths) -> None:
    node, _ = node_ops.add_node("Sediment", root=paths.root)
    add_reference("lee2021", "Sediment budgets", root=paths.root)
    result = EvidenceGapsScanResult(
        gaps=[_gap("Weak support.")],
        suggested_evidence_links=[EvidenceLinkSuggestion(target_id=node.id, bibkey="lee2021")],
    )
    created = result.apply(paths)
    assert created[0].startswith("question_")
    assert created[1] == f"evidence:lee2021->{node.id}/existence"


def test_gap_section_must_be_an_interpret_section() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EvidenceGap(section_type="not_a_section", gap_description="x")
