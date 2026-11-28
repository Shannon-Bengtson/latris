"""Server route tests for /api/toc/*: process tracing priors."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import process_tracing as pt
from latris.operations import toc
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "programme"
    init_project(root, statement="Does the programme work?")
    for n in ("Training", "Skills", "Other"):
        node_ops.add_node(n, root=root)
    edge_ops.add_edge("Training", "Skills", root=root)
    edge_ops.add_edge("Other", "Skills", root=root)
    toc.set_level("Training", "activity", root=root)
    toc.set_level("Skills", "output", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def test_prior(client: TestClient, project: Path) -> None:
    r = client.post("/api/toc/prior", json={"link": "Training -> Skills", "prior": 0.7, "source_id": "evaluation",
                                            "notes": "past cohorts"})
    assert r.status_code == 200
    body = r.json()
    assert (body["result"]["prior"], body["result"]["source_id"], body["result"]["notes"]) == (
        0.7, "evaluation", "past cohorts")
    assert body["commit_sha"] == git.head_sha(project)
    (entry,) = pt.get_priors(root=project).entries
    edge = next(e for e in edge_ops.list_edges(root=project) if e.id == entry.target_id)
    assert entry.prior == 0.7 and edge.id == body["result"]["target_id"]
    assert client.get("/api/toc/trace").json()["priors"][0]["prior"] == 0.7

    # Setting it again replaces it.
    assert client.post("/api/toc/prior", json={"link": "Training -> Skills", "prior": 0.4}).status_code == 200
    assert [e.prior for e in pt.get_priors(root=project).entries] == [0.4]


@pytest.mark.parametrize(("body", "status", "detail"), [
    ({"link": "Training -> Skills", "prior": 1.7}, 422, "less than 1"),
    ({"link": "Training -> Skills", "prior": 0}, 422, "greater than 0"),
    ({"link": "Training -> Skills", "prior": 0.5, "origin": "bogus"}, 422, "origin"),
    ({"link": "Training -> Skills", "prior": 0.5, "verification": "bogus"}, 422, "verification"),
    ({"link": "Training", "prior": 0.5}, 422, "is a factor"),
    ({"link": "Other -> Skills", "prior": 0.5}, 422, "give both ends a level"),
    ({"link": "Skills -> Training", "prior": 0.5}, 404, "no link"),
    ({"link": "edge_NOPE", "prior": 0.5}, 404, "edge_NOPE"),
])
def test_prior_errors(client: TestClient, project: Path, body: dict, status: int, detail: str) -> None:
    r = client.post("/api/toc/prior", json=body)
    assert r.status_code == status and detail in r.json()["detail"]
    assert pt.get_priors(root=project).entries == []


def test_prior_needs_a_number(client: TestClient) -> None:
    assert client.post("/api/toc/prior", json={"link": "Training -> Skills"}).status_code == 422
