"""Routes for what was command-line only: SD clock and taking a factor out of the simulation, BN weighted
tables and taking a factor out of the network, the model as a build spec."""

from __future__ import annotations

from fastapi.testclient import TestClient

from latris.server.app import create_app


def test_sd_settings_round_trip_and_are_validated(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    r = c.post("/api/sd/settings", json={"time_units": "month", "final_time": 36})
    assert r.status_code == 200 and r.json()["commit_sha"]
    s = c.get("/api/sd/settings").json()
    assert s["time_units"] == "month" and s["final_time"] == 36
    assert c.post("/api/sd/settings", json={}).status_code == 422  # nothing to set


def test_sd_unset_role_keeps_the_factor(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    r = c.delete("/api/sd/role/Drain Rate")
    assert r.status_code == 200 and r.json()["result"]["removed"] >= 1
    assert "Drain Rate" in {n["label"] for n in c.get("/api/nodes").json()}
    assert r.json()["result"]["target_id"] not in {e["target_id"] for e in c.get("/api/sd/roles").json()["roles"]}


def test_bn_weighted_table_and_remove_states(two_node_project_root):
    c = TestClient(create_app(project_root=two_node_project_root))
    for node in ("Price", "Demand"):
        assert c.post("/api/bn/state-space", json={"node": node, "states": ["low", "high"]}).status_code == 200
    r = c.post("/api/bn/weighted", json={"node": "Demand", "base": [0.5, 0.5], "weights": {"Price": {"high": -1.0}}})
    assert r.status_code == 200, r.text
    assert c.delete("/api/bn/state-space/Price").status_code == 422  # Demand's table uses it
    assert c.delete("/api/bn/state-space/Demand").status_code == 200


def test_export_spec_is_what_build_reads(sd_bathtub_root):
    from latris.operations.share_link import export_spec, spec_data

    c = TestClient(create_app(project_root=sd_bathtub_root))
    data = c.get("/api/export/spec", params={"model_type": "sd"}).json()
    assert data == spec_data(export_spec(model_type="sd", root=sd_bathtub_root)[1])
    assert data["model_type"] == "sd" and data["factors"]
