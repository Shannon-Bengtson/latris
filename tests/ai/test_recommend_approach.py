"""RecommendApproach context — structural fit (feedback loops vs acyclic
formalisms is derived from the registry and threaded into the prompt)."""

from __future__ import annotations

from pathlib import Path

from latris.ai.context import build_context
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


def _candidates(*ids: str) -> list[dict]:
    return [{"id": i, "name": i.upper(), "best_for": "x"} for i in ids]


def test_recommend_flags_acyclic_formalisms_when_loops_present(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    edge_ops.add_edge(b.id, a.id, kind="causal", root=root)  # closes a loop
    monkeypatch.chdir(root)

    pack = build_context(
        "RecommendApproach",
        {"candidates": _candidates("bn", "cld"), "evidence_summary": "none"},
        ProjectPaths(root),
    )
    user = pack.user
    assert "feedback loop" in user.lower()
    # BN requires acyclicity → flagged as not representable here.
    assert "REQUIRES AN ACYCLIC" in user
    # CLD is built around loops → noted as having them.
    assert "built around feedback loops (the current structure has them)" in user


def test_recommend_acyclic_ok_when_no_loops(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "proj"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("A", kind="variable", root=root)
    b, _ = node_ops.add_node("B", kind="variable", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)  # acyclic
    monkeypatch.chdir(root)

    pack = build_context(
        "RecommendApproach",
        {"candidates": _candidates("dag"), "evidence_summary": "n"},
        ProjectPaths(root),
    )
    assert "acyclic (no feedback loops)" in pack.user
    assert "so this fits" in pack.user
