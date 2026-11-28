"""Context for the configure prompts: SuggestEdgePolarities and RecommendApproach."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.context import build_context
from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.evidence import add_evidence
from latris.operations.init import init_project
from latris.operations.provenance import add_assumption
from latris.operations.references import add_reference
from latris.operations.view_attributes import set_view_attribute
from latris.repo.layout import ProjectPaths


@pytest.fixture
def model(tmp_path: Path, git_identity):
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    price, _ = node_ops.add_node("Price", kind="variable", root=root)
    demand, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(price.id, demand.id, kind="causal", root=root)
    return ProjectPaths(root), price, demand, edge


def _polarities(paths: ProjectPaths, edge, **inputs):
    edges = [{"edge_id": edge.id, "from_label": "Price", "to_label": "Demand"}]
    return build_context("SuggestEdgePolarities", {"model_type": "cld", "edges": edges, **inputs}, paths)


# ── SuggestEdgePolarities ────────────────────────────────────────────────────


def test_polarity_context_carries_node_and_edge_descriptions(model) -> None:
    paths, price, demand, edge = model
    attr_ops.set_attribute(price.id, "description", "Retail price " + "p" * 200, root=paths.root)
    attr_ops.set_attribute(demand.id, "description", "Units sold per week.", root=paths.root)
    attr_ops.set_attribute(edge.id, "description", "Higher prices deter buyers.", root=paths.root)

    pack = _polarities(paths, edge)
    assert pack.target_ids == [edge.id]
    assert pack.related_attributes == ["polarity"]
    assert f"edge_id={edge.id}: Price (variable) → Demand (variable)" in pack.user
    from_line = next(ln for ln in pack.user.splitlines() if "from desc:" in ln)
    assert from_line.strip() == "from desc: " + ("Retail price " + "p" * 200)[:120]
    assert "to desc: Units sold per week." in pack.user
    assert "edge description: Higher prices deter buyers." in pack.user
    assert "current polarity" not in pack.user  # nothing set yet
    assert "# Edges to analyse (1)" in pack.user


def test_polarity_context_lists_already_set_values(model) -> None:
    paths, _, _, edge = model
    set_view_attribute(edge.id, "cld", "polarity", "-", root=paths.root)
    pack = _polarities(paths, edge)
    assert "Already-set polarity values" in pack.user
    assert f"  - {edge.id}: -" in pack.user
    assert "current polarity: - (already set" in pack.user


def test_polarity_context_caps_assumptions_at_three(model) -> None:
    paths, _, _, edge = model
    for i in range(5):
        add_assumption(f"assumption number {i}", target_id=edge.id, root=paths.root)
    pack = _polarities(paths, edge)
    line = next(ln for ln in pack.user.splitlines() if "assumptions:" in ln)
    assert line.count("assumption number") == 3


def test_reference_hint_adds_the_evidence_block_with_titles(model) -> None:
    paths, price, _, edge = model
    add_reference("smith2020", "Price elasticity of demand", root=paths.root)
    add_reference("lee2019", "Unrelated", root=paths.root)
    add_evidence(edge.id, "existence", "smith2020", root=paths.root)
    add_evidence(price.id, "existence", "lee2019", root=paths.root)  # not on the analysed edge

    plain = _polarities(paths, edge)
    assert "Evidence attached to these edges" not in plain.user
    assert "evidence: smith2020" in plain.user  # the per-edge line is always there

    pack = _polarities(paths, edge, source_hint="references")
    assert "Evidence attached to these edges" in pack.user
    assert f"smith2020 → {edge.id}/existence (Price elasticity of demand)" in pack.user
    assert "lee2019" not in pack.user


def test_reference_hint_with_no_evidence_adds_no_block(model) -> None:
    paths, _, _, edge = model
    pack = _polarities(paths, edge, source_hint="references")
    assert "Evidence attached to these edges" not in pack.user


def test_an_edge_not_in_the_model_is_still_listed_without_detail(model) -> None:
    paths, _, _, _ = model
    pack = build_context(
        "SuggestEdgePolarities",
        {"model_type": "cld", "edges": [{"edge_id": "edge_GONE", "from_label": "A", "to_label": "B"}]},
        paths,
    )
    assert "edge_id=edge_GONE: A → B" in pack.user
    assert pack.target_ids == ["edge_GONE"]


@pytest.mark.parametrize(("model_type", "attr"), [("fcm", "weight"), ("not-a-type", "weight")])
def test_weighted_and_unknown_types_ask_for_a_weight(model, model_type, attr) -> None:
    paths, _, _, edge = model
    pack = build_context(
        "SuggestEdgePolarities",
        {"model_type": model_type, "edges": [{"edge_id": edge.id, "from_label": "Price", "to_label": "Demand"}]},
        paths,
    )
    assert pack.related_attributes == [attr]
    assert "weight (float in [-1, +1])" in pack.user


# ── RecommendApproach ────────────────────────────────────────────────────────


def test_recommend_without_candidates_or_evidence_says_so(model) -> None:
    paths, *_ = model
    pack = build_context("RecommendApproach", {}, paths)
    assert "(no candidate formalisms supplied)" in pack.user
    assert "(no evidence summarised)" in pack.user
    assert "2 node(s), 1 edge(s)" in pack.user


def test_recommend_on_an_empty_model_is_acyclic(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    pack = build_context("RecommendApproach", {"candidates": [{"id": "cld", "name": "CLD"}]}, ProjectPaths(root))
    assert "0 node(s), 0 edge(s)" in pack.user
    assert "acyclic (no feedback loops)" in pack.user
    assert "built around feedback loops (the current structure has none yet)" in pack.user


def test_recommend_an_unregistered_candidate_is_described_neutrally(model) -> None:
    paths, *_ = model
    pack = build_context(
        "RecommendApproach",
        {"candidates": [{"id": "my-own-method", "best_for": "anything"}]},
        paths,
    )
    assert "- my-own-method: my-own-method — best for: anything; structural fit: handles feedback loops" in pack.user
