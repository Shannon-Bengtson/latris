"""Routes the app reads on most screens: readiness, report configuration, model choices, identity."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import build as build_ops
from latris.operations.init import init_project
from latris.server.app import create_app

SPEC = """
factors:
  - {label: Workload}
  - {label: Burnout}
  - {label: Departures}
links:
  - {from: Workload, to: Burnout, polarity: "+"}
  - {from: Burnout, to: Departures, polarity: "+"}
  - {from: Departures, to: Workload, polarity: "+"}
"""


@pytest.fixture
def client(tmp_path: Path, git_identity) -> TestClient:
    root = tmp_path / "p"
    init_project(root, statement="Why do volunteers leave?")
    build_ops.build_from_spec(build_ops.load_spec(SPEC), root=root)
    return TestClient(create_app(project_root=root))


def test_readiness_build_interpret_and_transitions(client: TestClient) -> None:
    client.post("/api/model-choices/select", json={"model_type_id": "cld", "rationale": "Feedback"})
    build = client.get("/api/readiness/build").json()
    assert "cld" in build["model_scores"]
    assert client.get("/api/readiness/interpret").status_code == 200
    lights = client.get("/api/readiness/transitions").json()["transitions"]
    assert [(t["from_phase"], t["to_phase"]) for t in lights][-1] == ("interpret", "communicate")


def test_model_choices_select_revise_retire(client: TestClient) -> None:
    assert client.post("/api/model-choices/select", json={"model_type_id": "fcm", "rationale": "Weights"}).status_code == 201
    assert "fcm" in client.get("/api/project").json()["selected_model_types"]
    assert client.post("/api/model-choices/revise", json={"model_type_id": "fcm", "rationale": "Strengths"}).status_code == 201
    choices = client.get("/api/state").json()["provenance"]["model_choices"]["entries"]
    assert [c["action"] for c in choices if c["model_type_id"] == "fcm"] == ["added", "revised"]
    assert client.post("/api/model-choices/retire", json={"model_type_id": "fcm"}).status_code == 201
    assert "fcm" not in client.get("/api/project").json()["selected_model_types"]


def test_report_config_round_trips(client: TestClient) -> None:
    config = client.get("/api/report-config", params={"model_type": "cld"}).json()["result"]
    config["voice"] = "plain"
    r = client.put("/api/report-config", json=config)
    assert r.status_code == 200, r.text
    assert client.get("/api/report-config", params={"model_type": "cld"}).json()["result"]["voice"] == "plain"


def test_identity(client: TestClient) -> None:
    r = client.get("/api/identity")
    assert r.status_code == 200 and "name" in r.json()
