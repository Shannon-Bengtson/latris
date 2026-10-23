"""Server route tests for /api/sd/*."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from latris.server.app import create_app


@pytest.fixture
def client(sd_bathtub_root) -> TestClient:
    return TestClient(create_app(project_root=sd_bathtub_root))


@pytest.fixture
def diagram_client(sd_diagram_root) -> TestClient:
    return TestClient(create_app(project_root=sd_diagram_root))


def test_reads(client):
    roles = client.get("/api/sd/roles").json()
    assert roles["count"] == 7
    eqs = client.get("/api/sd/equations").json()
    assert {e["expression"] for e in eqs["equations"]} == {"inflow_rate", "water * drain_rate"}
    assert client.get("/api/sd/stocks").json()["stocks"][0]["units"] == "liter"
    assert client.get("/api/sd/constants").json()["count"] == 2
    assert client.get("/api/sd/tables").json()["count"] == 0


def test_check_ready(client):
    assert client.get("/api/sd/check").json() == {"ready": True, "gaps": []}


def test_check_not_ready(diagram_client):
    body = diagram_client.get("/api/sd/check").json()
    assert body["ready"] is False
    assert {g["gap_type"] for g in body["gaps"]} == {"unclassified", "no_stocks"}
    assert all(g["element_label"] for g in body["gaps"])


def test_mutations(diagram_client):
    r = diagram_client.post("/api/sd/role", json={"node": "Water", "role": "stock"})
    assert r.status_code == 200 and r.json()["commit_sha"]
    r = diagram_client.post("/api/sd/stocks", json={"node": "Water", "value": 3, "units": "liter"})
    assert r.status_code == 200 and r.json()["result"]["initial_value"] == 3

    r = diagram_client.post("/api/sd/role", json={"node": "Water", "role": "reservoir"})
    assert r.status_code == 400

    diagram_client.post("/api/sd/role", json={"node": "Drain Rate", "role": "constant"})
    r = diagram_client.post("/api/sd/constants", json={"node": "Drain Rate", "value": 0.1, "units": "1/year"})
    assert r.status_code == 200

    diagram_client.post("/api/sd/role", json={"node": "Outflow", "role": "flow"})
    r = diagram_client.post("/api/sd/equation", json={"node": "Outflow", "expression": "water * drain_rate",
                                                      "units": "liter/year"})
    assert r.status_code == 200 and r.json()["result"]["expression"] == "water * drain_rate"
    r = diagram_client.post("/api/sd/equation", json={"node": "Outflow", "expression": "water +",
                                                      "units": "liter/year"})
    assert r.status_code == 400 and "cannot parse" in r.json()["detail"]

    r = diagram_client.post("/api/sd/tables", json={
        "node": "Outflow", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
        "x_units": "dimensionless", "y_units": "dimensionless",
    })
    assert r.status_code == 200 and len(r.json()["result"]["points"]) == 2


def test_simulate(client):
    pytest.importorskip("scipy")
    r = client.post("/api/sd/simulate", json={"final_time": 10, "saveper": 5, "record": True})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["success"] is True
    assert body["result"]["times"] == [0.0, 5.0, 10.0]
    assert body["run_id"] and body["commit_sha"]


def test_simulate_rejects_bad_requests(client):
    assert client.post("/api/sd/simulate", json={"method": "midpoint"}).status_code == 422
    assert client.post("/api/sd/simulate", json={"final_time": -1, "record": False}).status_code == 400


def test_simulate_incomplete_model(diagram_client):
    r = diagram_client.post("/api/sd/simulate", json={"record": False})
    assert r.status_code == 400 and "not ready to simulate" in r.json()["detail"]
