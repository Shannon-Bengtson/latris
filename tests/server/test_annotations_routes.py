"""Coverage for the annotation-summary route across every annotation kind.

Exercises both the per-target and project-level (``target_id is None``)
branches for evidence, challenges, assumptions, decisions, questions and
sign-offs — the bulk of ``server/routes/annotations.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import challenges as ch_ops
from latris.operations import provenance as prov_ops
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model
from latris.schema import EvidenceLink, EvidenceLinkSet
from latris.server.app import create_app


@pytest.fixture
def client(two_node_project_root: Path) -> TestClient:
    return TestClient(create_app(project_root=two_node_project_root))


def _edge_id(project: Path) -> str:
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    paths = ProjectPaths(project)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    return substrate.edges[0].id


def test_summary_empty_has_no_counts(client: TestClient) -> None:
    data = client.get("/api/annotations/summary").json()
    assert data["per_target"] == {}
    assert data["global"] == {}


def test_evidence_per_target_and_global(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)
    paths = ProjectPaths(project)
    dump_model(
        EvidenceLinkSet(
            entries=[
                EvidenceLink(
                    target_id=edge_id, attribute="description", bibkey="ref1"
                ),
                EvidenceLink(
                    target_id=None, attribute="model", bibkey="ref2"
                ),
            ]
        ),
        paths.evidence_links_yaml,
    )

    data = client.get("/api/annotations/summary").json()
    assert data["per_target"][edge_id]["evidence"] == 1
    assert data["global"]["evidence"] == 1


def test_challenge_per_target_and_global(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)
    ch_ops.open_challenge(edge_id, "Direction is wrong", root=project)
    # Project-level challenge (no target_id).
    ch_ops.open_challenge(None, "Scope is too narrow", root=project)

    data = client.get("/api/annotations/summary").json()
    assert data["per_target"][edge_id]["challenge"] == 1
    assert data["global"]["challenge"] == 1


def test_assumption_per_target_and_global(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)
    prov_ops.add_assumption("Holds locally", target_id=edge_id, root=project)
    prov_ops.add_assumption("Holds globally", target_id=None, root=project)

    data = client.get("/api/annotations/summary").json()
    assert data["per_target"][edge_id]["assumption"] == 1
    assert data["global"]["assumption"] == 1


def test_decision_per_target_and_global(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)
    prov_ops.log_decision("Keep edge", "rationale", target_id=edge_id, root=project)
    prov_ops.log_decision("Use CLD", "rationale", target_id=None, root=project)

    data = client.get("/api/annotations/summary").json()
    assert data["per_target"][edge_id]["decision"] == 1
    assert data["global"]["decision"] == 1


def test_question_per_target_and_global(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)
    prov_ops.add_question("Is this causal?", target_id=edge_id, root=project)
    prov_ops.add_question("What is the boundary?", target_id=None, root=project)

    data = client.get("/api/annotations/summary").json()
    assert data["per_target"][edge_id]["question"] == 1
    assert data["global"]["question"] == 1


def test_signoff_per_target_and_global(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)
    prov_ops.record_signoff(target_id=edge_id, root=project)
    prov_ops.record_signoff(target_id=None, root=project)

    data = client.get("/api/annotations/summary").json()
    assert data["per_target"][edge_id]["signoff"] == 1
    assert data["global"]["signoff"] == 1


def test_multiple_kinds_on_same_target_accumulate(
    client: TestClient, two_node_project_root: Path
) -> None:
    project = two_node_project_root
    edge_id = _edge_id(project)
    prov_ops.add_assumption("A1", target_id=edge_id, root=project)
    prov_ops.add_question("Q1", target_id=edge_id, root=project)
    ch_ops.open_challenge(edge_id, "C1", root=project)

    counts = client.get("/api/annotations/summary").json()["per_target"][edge_id]
    assert counts["assumption"] == 1
    assert counts["question"] == 1
    assert counts["challenge"] == 1
