"""LATRIS_DEFAULT_ORIGIN: agents' work isn't recorded as a person's."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.findings import record_new_finding
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import DescriptionSet, EvidenceLinkSet, PolaritySet, Substrate


def _build(root: Path):
    a, _ = node_ops.add_node("A", root=root)
    b, _ = node_ops.add_node("B", root=root)
    e, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    attr_ops.set_attribute(a.id, "description", "Thing A.", root=root)
    view_attr_ops.set_view_attribute(e.id, "cld", "polarity", "+", root=root)
    ref_ops.add_reference("k", "T", root=root)
    evidence_ops.add_evidence(e.id, "polarity", "k", root=root)
    finding, _ = record_new_finding("A drives B.", "structure", "cld", root=root)
    return e, finding


def _origins(root: Path, finding) -> set[str]:
    paths = ProjectPaths(root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    pol = load_model(PolaritySet, paths.view_attribute_path("cld", "polarity"))
    return (
        {x.origin for x in sub.entities}
        | {x.origin for x in sub.edges}
        | {x.origin for x in load_model(DescriptionSet, paths.descriptions_yaml).entries}
        | {x.origin for x in pol.entries}
        | {x.origin for x in load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries}
        | {finding.origin}
    )


def test_defaults_to_human_direct(tmp_path: Path, git_identity, monkeypatch) -> None:
    monkeypatch.delenv("LATRIS_DEFAULT_ORIGIN", raising=False)
    root = tmp_path / "p"
    init_project(root, statement="Q?")
    _, finding = _build(root)
    assert _origins(root, finding) == {"human-direct"}


def test_agent_work_is_marked_ai_proposed(tmp_path: Path, git_identity, monkeypatch) -> None:
    monkeypatch.setenv("LATRIS_DEFAULT_ORIGIN", "ai-proposed")
    root = tmp_path / "p"
    init_project(root, statement="Q?")
    _, finding = _build(root)
    assert _origins(root, finding) == {"ai-proposed"}


def test_existing_files_keep_their_origin(tmp_path: Path, git_identity, monkeypatch) -> None:
    monkeypatch.delenv("LATRIS_DEFAULT_ORIGIN", raising=False)
    root = tmp_path / "p"
    init_project(root, statement="Q?")
    node_ops.add_node("Human", root=root)
    monkeypatch.setenv("LATRIS_DEFAULT_ORIGIN", "ai-proposed")
    node_ops.add_node("Agent", root=root)
    sub = load_model(Substrate, ProjectPaths(root).conceptual_yaml)
    assert {e.label: e.origin for e in sub.entities} == {"Human": "human-direct", "Agent": "ai-proposed"}


def test_rejects_unknown_origin(tmp_path: Path, git_identity, monkeypatch) -> None:
    monkeypatch.setenv("LATRIS_DEFAULT_ORIGIN", "robot")
    root = tmp_path / "p"
    init_project(root, statement="Q?")
    with pytest.raises(ValueError, match="LATRIS_DEFAULT_ORIGIN"):
        node_ops.add_node("A", root=root)
