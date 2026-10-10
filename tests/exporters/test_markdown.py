from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from latris.exporters import markdown as md
from latris.operations import attributes as attr_ops
from latris.operations import challenges as ch_ops
from latris.operations import edges as edge_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import provenance as prov_ops
from latris.operations import references as ref_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def rich_project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)

    attr_ops.set_attribute(a.id, "description", "Posted retail price.", root=root)
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
    attr_ops.set_attribute(edge.id, "confidence", "medium", root=root)

    ref_ops.add_reference(
        "smith2023",
        title="Pricing effects",
        authors=["Smith, J."],
        year=2023,
        doi="10.1000/x",
        root=root,
    )
    evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=root)

    prov_ops.add_assumption("Market is liquid", rationale="Industry norm.", root=root)
    prov_ops.log_decision("Excluded macro shocks", "Out of scope", root=root)
    prov_ops.record_signoff(role="Senior reviewer", scope="Substrate v0.1", root=root)
    prov_ops.record_session(date(2026, 4, 10), ["Alice", "Bob"], notes="Kickoff.", root=root)
    prov_ops.add_question("Seasonality?", root=root)
    prov_ops.add_exclusion("Cross-border effects", "Scope of study.", root=root)
    prov_ops.add_prediction("Demand drops 8%", horizon="6 months", root=root)

    ch, _ = ch_ops.open_challenge(edge.id, "Simultaneity bias", attribute="polarity", root=root)
    ch_closed, _ = ch_ops.open_challenge(edge.id, "Old argument", root=root)
    ch_ops.resolve_challenge(ch_closed.id, "retained-unchanged", rationale="Robust to the critique.", root=root)

    return root


def test_markdown_has_all_sections(rich_project: Path) -> None:
    paths = ProjectPaths(rich_project)
    out = md.render(paths)

    for section in (
        "# Does X cause Y?",
        "## Nodes",
        "## Edges",
        "## Evidence",
        "## Assumptions",
        "## Decisions",
        "## Sign-offs",
        "## Sessions",
        "## Open questions",
        "## Exclusions",
        "## Predictions",
        "## Challenges",
        "### Open",
        "### Resolved",
        "## References",
        "## Elicitation Sessions",
        "## Datasets",
        "## Data Actions",
        "## Analysis Runs",
        "## Milestones",
    ):
        assert section in out, f"missing section: {section}"


def test_markdown_surfaces_domain_content(rich_project: Path) -> None:
    paths = ProjectPaths(rich_project)
    out = md.render(paths)

    assert "Price" in out and "Demand" in out
    assert "Posted retail price." in out
    assert "smith2023" in out
    assert "Market is liquid" in out
    assert "Simultaneity bias" in out
    assert "retained-unchanged" in out
    assert "Seasonality?" in out


def test_markdown_polarity_shows_in_edge_table(rich_project: Path) -> None:
    paths = ProjectPaths(rich_project)
    out = md.render(paths)
    # Find the edges block and confirm "-" polarity is rendered.
    edges_idx = out.index("## Edges")
    evidence_idx = out.index("## Evidence")
    edges_block = out[edges_idx:evidence_idx]
    assert "Price → Demand" in edges_block
    assert "| - |" in edges_block  # polarity cell
    assert "medium" in edges_block


def test_markdown_empty_project_still_renders(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "empty"
    init_project(root, statement="Do X.")
    out = md.render(ProjectPaths(root))
    assert "# Do X." in out
    assert "_No nodes yet._" in out
    assert "_No edges yet._" in out
    assert "_No evidence attached yet._" in out


def test_markdown_renders_foundation_predictions(tmp_path: Path, git_identity) -> None:
    """foundation.predictions surfaces as a 'Pre-modelling intuition' block
    above model structure, so reviewers can compare AI findings to the
    human prior recorded at init time."""
    from latris.operations.project import set_foundation_field

    root = tmp_path / "with_predictions"
    init_project(root, statement="Should we adopt X?")
    set_foundation_field(
        "predictions",
        "Likely positive for retention; dominant risk is client coverage.",
        root=root,
    )
    out = md.render(ProjectPaths(root))
    assert "## Pre-modelling intuition" in out
    assert "Likely positive for retention" in out
    # Block should appear before model structure / nodes so reviewers
    # see the prior before reading the AI's answer.
    intuition_idx = out.index("## Pre-modelling intuition")
    nodes_idx = out.index("## Nodes")
    assert intuition_idx < nodes_idx


def test_markdown_omits_empty_foundation_predictions(tmp_path: Path, git_identity) -> None:
    """When foundation.predictions is empty, no Pre-modelling intuition
    block is emitted — avoids a noisy heading on every report."""
    root = tmp_path / "no_predictions"
    init_project(root, statement="Q?")
    out = md.render(ProjectPaths(root))
    assert "## Pre-modelling intuition" not in out


def test_markdown_filters_meta_open_questions(tmp_path: Path, git_identity) -> None:
    """Open questions about prompt internals (Tier-0, source extract, etc.)
    must be filtered out of the rendered open-questions section. The
    4DWW capability run leaked one of these into the partner report —
    defensive filter prevents recurrence even if the prompt fails.
    """
    root = tmp_path / "meta_q"
    init_project(root, statement="Q?")
    # A legitimate question and several meta-questions.
    prov_ops.add_question(
        "How sensitive is Client Coverage to reduced working days?",
        root=root,
    )
    prov_ops.add_question(
        "The Tier-0 source content for this target was empty. Should I proceed?",
        root=root,
    )
    prov_ops.add_question(
        "Is the source extract sufficient as per instructions?",
        root=root,
    )

    out = md.render(ProjectPaths(root))
    open_idx = out.index("## Open questions")
    next_section = out.index("## Exclusions")
    block = out[open_idx:next_section]
    assert "Client Coverage" in block
    assert "Tier-0" not in block
    assert "as per instructions" not in block


def test_markdown_splits_edges_by_kind(tmp_path: Path, git_identity) -> None:
    """Policy/governance/definitional edges render under a separate
    '### Policy regime' sub-block, distinct from the causal substrate.
    The 4DWW capability artefact rendered all edges in one table, hiding
    that two decision_rule edges back to '4-Day Work Week' weren't
    feedback mechanism."""
    root = tmp_path / "edge_split"
    init_project(root, statement="Adopt 4-day week?")
    a, _ = node_ops.add_node("Hours", root=root)
    b, _ = node_ops.add_node("Output", root=root)
    p, _ = node_ops.add_node("Policy", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    edge_ops.add_edge(b.id, p.id, kind="decision_rule", root=root)

    out = md.render(ProjectPaths(root))
    causal_idx = out.index("### Causal substrate")
    policy_idx = out.index("### Policy regime")
    assert causal_idx < policy_idx
    # Causal edge appears in the causal block, decision_rule in policy.
    causal_block = out[causal_idx:policy_idx]
    policy_block = out[policy_idx:]
    assert "Hours → Output" in causal_block
    assert "Output → Policy" in policy_block
    assert "excluded from loop and centrality analysis" in policy_block


def test_markdown_omits_empty_policy_regime_block(tmp_path: Path, git_identity) -> None:
    """When no policy/governance edges exist, the '### Policy regime'
    sub-block is suppressed to avoid an empty heading on every report."""
    root = tmp_path / "no_policy"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("A", root=root)
    b, _ = node_ops.add_node("B", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)

    out = md.render(ProjectPaths(root))
    assert "### Causal substrate" in out
    assert "### Policy regime" not in out


def test_markdown_write_to_file(rich_project: Path) -> None:
    paths = ProjectPaths(rich_project)
    target = rich_project / "reports" / "exports" / "summary.md"
    md.write(paths, target)
    assert target.is_file()
    assert "Does X cause Y?" in target.read_text(encoding="utf-8")
