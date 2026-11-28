"""Context for the element-scope prompts: explain, challenge, cite, steelman, fill a field."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai import interactions as inter_ops
from latris.ai.context import build_context
from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.evidence import add_evidence
from latris.operations.init import init_project
from latris.operations.provenance import add_exclusion
from latris.operations.references import add_reference
from latris.repo.layout import ProjectPaths


@pytest.fixture
def model(tmp_path: Path, git_identity):
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    price, _ = node_ops.add_node("Price", kind="variable", root=root)
    demand, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(price.id, demand.id, kind="causal", root=root)
    return ProjectPaths(root), price, demand, edge


def _record(paths: ProjectPaths, target_id: str, summary: str, adoption: str = "approved") -> None:
    inter_ops.record_interaction(
        prompt_name="ExplainThisElement", prompt_inputs={}, model_id="mock", response_summary=summary,
        target_ids=[target_id], adoption=adoption, root=paths.root,
    )


# ── ExplainThisElement ───────────────────────────────────────────────────────


def test_explain_an_edge_names_both_ends(model) -> None:
    paths, price, demand, edge = model
    attr_ops.set_attribute(edge.id, "description", "Dearer goods sell less.", root=paths.root)
    pack = build_context("ExplainThisElement", {"target_id": edge.id}, paths)

    assert f"- from: Price ({price.id})" in pack.user
    assert f"- to: Demand ({demand.id})" in pack.user
    assert "- edge_kind: causal" in pack.user
    assert "- description = {'value': 'Dearer goods sell less.'" in pack.user
    assert pack.target_ids == [edge.id]
    assert pack.related_attributes == ["description"]
    # An edge's own neighbour lists are empty.
    assert "## Inbound edges\n_(none)_\n## Outbound edges\n_(none)_" in pack.user


def test_explain_a_node_lists_its_links_and_prior_interactions(model) -> None:
    paths, price, _, edge = model
    _record(paths, price.id, "Price is the lever.")
    pack = build_context("ExplainThisElement", {"target_id": "Price"}, paths)  # by label
    assert "- label: Price" in pack.user
    assert "Outbound edges" in pack.user and edge.id in pack.user
    assert "Prior interactions on this target" in pack.user
    assert "Price is the lever." in pack.user


# ── ChallengeThisConnection ──────────────────────────────────────────────────


def test_challenge_a_node(model) -> None:
    paths, price, _, _ = model
    attr_ops.set_attribute(price.id, "description", "Posted price.", root=paths.root)
    pack = build_context("ChallengeThisConnection", {"target_id": price.id}, paths)
    assert "# Target to challenge\n" in pack.user
    assert "- kind: node" in pack.user and "- label: Price" in pack.user
    assert pack.target_ids == [price.id]
    assert pack.related_attributes == ["description"]


def test_challenge_an_edge_attribute_includes_its_ends_and_history(model) -> None:
    paths, price, demand, edge = model
    add_reference("r1", "Elasticity", root=paths.root)
    add_reference("r2", "Pricing", root=paths.root)
    add_evidence(edge.id, "existence", "r1", root=paths.root)
    add_evidence(edge.id, "existence", "r2", root=paths.root)
    from latris.operations.evidence import remove_evidence

    remove_evidence(edge.id, "existence", "r1", rationale="wrong market", root=paths.root)
    pack = build_context("ChallengeThisConnection", {"target_id": edge.id, "target_attribute": "polarity"}, paths)

    assert "# Target to challenge (attribute: polarity)" in pack.user
    assert "- from: Price" in pack.user and "- to: Demand" in pack.user
    assert "Recent history for this element" in pack.user
    assert "wrong market" in pack.user
    assert pack.target_ids == [edge.id, price.id, demand.id]
    assert pack.related_attributes == ["polarity"]


# ── SuggestCitations ─────────────────────────────────────────────────────────


def test_citations_for_a_node_show_library_existing_links_and_exclusions(model) -> None:
    paths, price, _, _ = model
    add_reference("smith2020", "Price elasticity", year=2020, root=paths.root)
    add_reference("lee2019", "Wages", root=paths.root)
    add_evidence(price.id, "description", "smith2020", notes="direct measure", root=paths.root)
    add_evidence(price.id, "existence", "lee2019", root=paths.root)  # another attribute: not listed
    attr_ops.set_attribute(price.id, "description", "Posted price.", root=paths.root)
    attr_ops.set_attribute(price.id, "confidence", "high", root=paths.root)
    add_exclusion("Wholesale markets are out of scope.", "retail question", root=paths.root)

    pack = build_context("SuggestCitations", {"target_id": price.id, "target_attribute": "description"}, paths)
    user = pack.user
    assert f"id: {price.id}\nattribute: description\nlabel: Price" in user
    current = user.split("## Current value of this attribute", 1)[1].split("##", 1)[0]
    assert "description = {'value': 'Posted price.'" in current
    assert "confidence" not in current  # only the attribute being cited
    assert "smith2020" in user and "lee2019" in user  # whole library
    evidence_block = user.split("Evidence already attached to this (target, attribute)", 1)[1]
    assert "direct measure" in evidence_block
    assert "lee2019" not in evidence_block.split("#", 1)[0]
    assert "Wholesale markets are out of scope." in user
    assert pack.related_attributes == ["description"]


def test_citations_for_an_edge_have_no_label(model) -> None:
    paths, _, _, edge = model
    pack = build_context("SuggestCitations", {"target_id": edge.id, "target_attribute": "existence"}, paths)
    assert f"id: {edge.id}\nattribute: existence\n\n" in pack.user
    assert "label:" not in pack.user.split("# Target", 1)[1].split("#", 1)[0]


# ── SteelmanOpposingView ─────────────────────────────────────────────────────


def test_steelman_a_node_shows_links_and_flags_prior_interactions_as_context(model) -> None:
    paths, price, _, edge = model
    _record(paths, price.id, "An earlier steelman.", adoption="rejected")
    pack = build_context("SteelmanOpposingView", {"target_id": price.id}, paths)
    assert "# Target element" in pack.user and "- label: Price" in pack.user
    assert "Outbound edges" in pack.user and edge.id in pack.user
    assert "An earlier steelman." in pack.user
    assert "for context only" in pack.user
    assert pack.target_ids == [price.id]


def test_steelman_an_edge_without_prior_interactions(model) -> None:
    paths, _, _, edge = model
    pack = build_context("SteelmanOpposingView", {"target_id": edge.id}, paths)
    assert "- from: Price" in pack.user and "- to: Demand" in pack.user
    assert "## Inbound edges\n_(none)_" in pack.user
    assert "for context only" not in pack.user


# ── FillProvenanceField ──────────────────────────────────────────────────────


def test_fill_field_on_a_node(model) -> None:
    paths, price, _, edge = model
    attr_ops.set_attribute(price.id, "description", "Posted price.", root=paths.root)
    pack = build_context(
        "FillProvenanceField",
        {"target_kind": "entity", "target_id": price.id, "field_path": "rationale", "current_value": "draft"},
        paths,
    )
    assert "# Target node\n- label: Price\n- kind: variable" in pack.user
    assert edge.id in pack.user  # its outbound link
    assert "Current value: 'draft'" in pack.user
    assert "# Field to fill\nrationale" in pack.user
    assert pack.target_ids == [price.id]
    assert pack.related_attributes == ["rationale", "description"]


def test_fill_field_on_an_edge_with_a_row(model) -> None:
    paths, _, _, edge = model
    pack = build_context(
        "FillProvenanceField",
        {"target_kind": "edge", "target_id": edge.id, "field_path": "assumptions.statement", "row_id": "assumption_1"},
        paths,
    )
    assert "# Target edge\n- from: Price\n- to: Demand\n- kind: causal" in pack.user
    assert "# Provenance row\n- row_id: assumption_1" in pack.user
    assert "Current value" not in pack.user


def test_fill_a_project_level_field(model) -> None:
    paths, *_ = model
    pack = build_context("FillProvenanceField", {"target_kind": "project", "field_path": "audience"}, paths)
    assert "# Target\nProject-level field." in pack.user
    assert pack.target_ids == []
    assert pack.related_attributes == ["audience"]


def test_fill_field_on_an_element_that_is_gone_adds_no_target_block(model) -> None:
    paths, *_ = model
    for kind in ("entity", "edge"):
        pack = build_context(
            "FillProvenanceField", {"target_kind": kind, "target_id": "node_GONE", "field_path": "rationale"}, paths
        )
        assert "# Target" not in pack.user
        assert "# Field to fill\nrationale" in pack.user
