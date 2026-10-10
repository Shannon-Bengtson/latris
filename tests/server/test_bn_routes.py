"""Tests for the Bayesian Network API endpoints."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import bn as bn_ops
from latris.operations.datasets import upload_dataset
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.server.app import create_app

pytest.importorskip("pgmpy")


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="BN routes test")
    rain, _ = add_node("Rain", kind="variable", root=root)
    wet, _ = add_node("Wet", kind="variable", root=root)
    add_edge(rain.id, wet.id, kind="causal", root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _quantify(client: TestClient) -> None:
    assert client.post("/api/bn/state-space", json={"node": "Rain", "states": ["yes", "no"]}).status_code == 200
    assert client.post("/api/bn/state-space", json={"node": "Wet", "states": ["yes", "no"]}).status_code == 200
    assert client.post("/api/bn/cpt", json={"node": "Rain", "probs": [0.2, 0.8]}).status_code == 200
    r = client.post("/api/bn/cpt", json={"node": "Wet", "parents": ["Rain"], "probs": [0.9, 0.1, 0.1, 0.9]})
    assert r.status_code == 200, r.text


def test_state_space_roundtrip(client: TestClient):
    resp = client.post("/api/bn/state-space", json={"node": "Rain", "states": ["yes", "no"]})
    assert resp.status_code == 200
    assert resp.json()["commit_sha"]

    listed = client.get("/api/bn/state-spaces").json()
    assert listed["count"] == 1
    assert listed["state_spaces"][0]["states"] == ["yes", "no"]


def test_cpt_shape_error(client: TestClient):
    client.post("/api/bn/state-space", json={"node": "Rain", "states": ["yes", "no"]})
    client.post("/api/bn/state-space", json={"node": "Wet", "states": ["yes", "no"]})
    resp = client.post("/api/bn/cpt", json={"node": "Wet", "parents": ["Rain"], "probs": [0.9, 0.1]})
    assert resp.status_code == 400
    assert "expected 4 probabilities" in resp.json()["detail"]


def test_check_then_ready(client: TestClient):
    before = client.get("/api/bn/check").json()
    assert before["ready"] is False
    assert before["gaps"]

    _quantify(client)
    after = client.get("/api/bn/check").json()
    assert after["ready"] is True
    assert after["gaps"] == []


def test_marginals(client: TestClient):
    _quantify(client)
    data = client.get("/api/bn/marginals").json()
    # marginals are keyed by node id, not label — find the wet node by its value.
    wet_dist = next(d for d in data["marginals"].values() if abs(d["yes"] - 0.26) < 1e-6)
    assert wet_dist["yes"] == pytest.approx(0.26, abs=1e-6)


def test_noisy_or_route_roundtrip_and_infer(client: TestClient, project: Path):
    # Rain (root) -> Wet via Noisy-OR (both binary).
    client.post("/api/bn/state-space", json={"node": "Rain", "states": ["yes", "no"]})
    client.post("/api/bn/state-space", json={"node": "Wet", "states": ["yes", "no"]})
    client.post("/api/bn/cpt", json={"node": "Rain", "probs": [0.2, 0.8]})
    resp = client.post(
        "/api/bn/noisy-or",
        json={
            "node": "Wet",
            "leak": 0.05,
            "causes": [{"parent": "Rain", "active_state": "yes", "prob": 0.8}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["commit_sha"]

    listed = client.get("/api/bn/noisy-or").json()
    assert listed["count"] == 1

    assert client.get("/api/bn/check").json()["ready"] is True
    # P(Wet=yes) = P(Rain=yes)·(1-(1-.05)(1-.8)) + P(Rain=no)·.05
    #            = 0.2·0.81 + 0.8·0.05 = 0.202
    data = client.get("/api/bn/marginals").json()
    wet = next(d for d in data["marginals"].values() if abs(d["yes"] - 0.202) < 1e-6)
    assert wet["yes"] == pytest.approx(0.202, abs=1e-6)


def test_learn_route_preview_and_apply(client: TestClient, project: Path, tmp_path: Path):
    # Dataset columns match node labels Rain/Wet.
    bn_ops.set_state_space("Rain", ["yes", "no"], root=project)
    bn_ops.set_state_space("Wet", ["yes", "no"], root=project)
    csv_path = tmp_path / "rw.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Rain", "Wet"])
        w.writerows([("yes", "yes")] * 30 + [("no", "no")] * 70)
    upload_dataset(csv_path, name="rw", root=project)

    preview = client.post("/api/bn/learn", json={"dataset": "rw", "estimator": "mle"}).json()
    assert preview["applied"] is False
    assert preview["rows_used"] == 100

    applied = client.post("/api/bn/learn", json={"dataset": "rw", "estimator": "mle", "apply": True}).json()
    assert applied["applied"] is True
    assert applied["commit_sha"] and applied["run_id"]
    assert client.get("/api/bn/check").json()["ready"] is True


def test_sensitivity_route(client: TestClient):
    _quantify(client)
    resp = client.post("/api/bn/sensitivity", json={"target": "Wet", "state": "yes"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_state"] == "yes"
    assert data["findings"]  # ranked parameters
    assert data["run_id"] and data["commit_sha"]  # recorded by default


def test_query_with_evidence(client: TestClient):
    _quantify(client)
    resp = client.post("/api/bn/query", json={"query": ["Rain"], "evidence": {"Wet": "yes"}})
    assert resp.status_code == 200
    marg = resp.json()["marginals"]
    rain_dist = next(iter(marg.values()))
    assert rain_dist["yes"] == pytest.approx(0.6923076923, abs=1e-6)

    bad = client.post("/api/bn/query", json={"evidence": {"Wet": "maybe"}})
    assert bad.status_code == 400
