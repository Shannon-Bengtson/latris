"""/api/workflow serves the stages, steps and tracks (schema/workflow.py), with no project needed."""

from fastapi.testclient import TestClient

from latris.schema import workflow as wf
from latris.server.app import create_app


def test_workflow_serves_the_registry(empty_project_root):
    c = TestClient(create_app(project_root=empty_project_root))
    body = c.get("/api/workflow").json()
    assert [s["id"] for s in body["stages"]] == list(wf.STAGE_IDS)
    analyse = next(s for s in body["stages"] if s["id"] == "analyse")
    assert [st["id"] for st in analyse["steps"]] == list(wf.step_ids("analyse"))
    assert [t["id"] for t in body["tracks"]] == list(wf.TRACK_IDS)
    assert body["composite"] == "composite"


def test_analyses_carry_their_step(empty_project_root):
    c = TestClient(create_app(project_root=empty_project_root))
    entries = c.get("/api/analyses", params={"model_type": "fault_tree"}).json()["analyses"]
    steps = {e["kind"]: e["step"] for e in entries}
    assert steps["ft-analysis"] == "analyse.base_case"
    assert steps["ft-monte-carlo"] == "analyse.uncertainty"
    assert steps["ft-gsa"] == "analyse.sensitivity"
