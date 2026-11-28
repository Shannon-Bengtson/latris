"""Server route tests for /api/bowtie/*: elements, uncertainty ranges and the Monte Carlo run."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import bow_tie as bt
from latris.operations import nodes as node_ops
from latris.operations import risk_uncertainty as ru
from latris.operations.analysis_results import list_results
from latris.operations.build import build_from_spec, load_spec
from latris.operations.init import init_project
from latris.repo import git
from latris.repo.project import require_project
from latris.server.app import create_app
from tests.operations.test_bow_tie import SPEC


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "containment"
    init_project(root, statement="How well protected are we against a loss of containment?")
    build_from_spec(load_spec(SPEC), root=root)
    return root


@pytest.fixture
def client(project: Path) -> TestClient:
    return TestClient(create_app(project_root=project))


def _id(root: Path, label: str) -> str:
    return next(e.id for e in node_ops.list_nodes(root=root) if e.label == label)


def _ranges(root: Path) -> dict[str, dict[str, float]]:
    return {k.split("|")[0]: e.params for k, e in ru.specs("bow_tie", require_project(root)).items()}


def test_element(client: TestClient, project: Path) -> None:
    r = client.post("/api/bowtie/element", json={"node": "Loss of containment", "element": "top_event"})
    assert r.status_code == 200
    assert r.json()["result"] == {"target_id": _id(project, "Loss of containment"), "element": "top_event"}
    assert r.json()["commit_sha"] == git.head_sha(project)
    assert bt.get_elements(root=project)[_id(project, "Loss of containment")] == "top_event"


def test_element_errors(client: TestClient, project: Path) -> None:
    before = bt.get_elements(root=project)
    bad = client.post("/api/bowtie/element", json={"node": "Fire", "element": "bogus"})
    assert bad.status_code == 422 and "not a bow-tie element" in bad.json()["detail"]
    assert client.post("/api/bowtie/element", json={"node": "Nope", "element": "threat"}).status_code == 404
    link = client.post("/api/bowtie/element", json={"node": "Gas detection -> Fire", "element": "barrier"})
    assert link.status_code == 422 and "is a link" in link.json()["detail"]
    assert bt.get_elements(root=project) == before


def test_uncertainty_set_list_clear(client: TestClient, project: Path) -> None:
    assert client.get("/api/bowtie/uncertainty").json() == {"uncertainty": [], "count": 0}
    r = client.post("/api/bowtie/uncertainty", json={"target": "Gas detection", "distribution": "uniform",
                                                     "params": {"min": 0.1, "max": 0.3}, "reason": "vendor data"})
    assert r.status_code == 200
    assert r.json()["result"]["params"] == {"min": 0.1, "max": 0.3}
    assert r.json()["result"]["parameter_cell_id"] == "bow_tie:pfd"
    assert r.json()["commit_sha"] == git.head_sha(project)
    # A median and error factor become a lognormal's mean and sd.
    r = client.post("/api/bowtie/uncertainty", json={"target": "Corrosion",
                                                     "params": {"median": 0.1, "error_factor": 3}})
    assert r.status_code == 200 and set(r.json()["result"]["params"]) >= {"mean", "sd"}

    listed = client.get("/api/bowtie/uncertainty").json()
    assert listed["count"] == 2
    assert {u["target_id"] for u in listed["uncertainty"]} == {_id(project, "Gas detection"), _id(project, "Corrosion")}
    assert _ranges(project)[_id(project, "Gas detection")] == {"min": 0.1, "max": 0.3}

    r = client.post("/api/bowtie/uncertainty", json={"target": "Corrosion", "clear": True})
    assert r.status_code == 200 and r.json()["result"] == {"cleared": "Corrosion"}
    assert set(_ranges(project)) == {_id(project, "Gas detection")}
    again = client.post("/api/bowtie/uncertainty", json={"target": "Corrosion", "clear": True})
    assert again.status_code == 422 and "no uncertainty range to clear" in again.json()["detail"]


@pytest.mark.parametrize(("body", "status", "detail"), [
    ({"target": "Fire", "distribution": "uniform", "params": {"min": 0.1, "max": 0.3}}, 422, "neither a barrier"),
    ({"target": "Nope", "distribution": "uniform", "params": {"min": 0.1, "max": 0.3}}, 404, "Nope"),
    ({"target": "Gas detection", "distribution": "bogus", "params": {"min": 0.1, "max": 0.3}}, 422, "distribution"),
    ({"target": "Gas detection", "distribution": "uniform", "params": {"min": 0.5, "max": 0.9}}, 422, "outside"),
    ({"target": "Gas detection", "distribution": "uniform", "params": {"min": 0.3, "max": 0.1}}, 422, "less than"),
    ({"target": "Gas detection", "distribution": "uniform", "params": {"min": 0.5, "max": 1.5}}, 422, "lie in"),
    # A range missing a bound is the request's fault (it once surfaced as a KeyError, read as a 404).
    ({"target": "Gas detection", "distribution": "uniform", "params": {}}, 422, "min"),
    ({"target": "Gas detection", "distribution": "triangular", "params": {"mode": 0.2, "max": 0.3}}, 422, "min"),
    ({"target": "Gas detection", "distribution": "lognormal", "params": {"median": 0.2}}, 422, "error factor"),
])
def test_uncertainty_errors(client: TestClient, project: Path, body: dict, status: int, detail: str) -> None:
    r = client.post("/api/bowtie/uncertainty", json=body)
    assert r.status_code == status, r.text
    assert detail in r.json()["detail"]
    assert _ranges(project) == {}


def test_monte_carlo(client: TestClient, project: Path) -> None:
    client.post("/api/bowtie/uncertainty", json={"target": "Gas detection", "distribution": "uniform",
                                                 "params": {"min": 0.1, "max": 0.3}})
    r = client.post("/api/bowtie/monte-carlo", json={"runs": 200, "seed": 1})
    assert r.status_code == 200
    body = r.json()
    res = body["result"]
    assert (res["model_type"], res["runs"], res["primary"]) == ("bow_tie", 200, "Loss of containment (per year)")
    top = next(o for o in res["outputs"] if o["output"] == res["primary"])
    assert top["point"] == pytest.approx(bt.analyse(root=project)["frequency"]["top"])
    assert res["run_id"] and body["commit_sha"] == git.head_sha(project)
    assert res["run_id"] in {run.id for run, _hidden, _stale in list_results(root=project)}

    # Not recorded: nothing committed.
    r = client.post("/api/bowtie/monte-carlo", json={"runs": 20, "output": "Fire", "record": False})
    assert r.status_code == 200 and r.json()["commit_sha"] is None
    assert r.json()["result"]["primary"] == "Fire (per year)" and "run_id" not in r.json()["result"]
    assert git.head_sha(project) == body["commit_sha"]


@pytest.mark.parametrize(("body", "detail"), [
    ({"runs": 0}, "runs must be between"),
    ({"runs": 10**9}, "runs must be between"),
    ({"runs": 20, "sampling": "bogus"}, "sampling must be"),
    ({"runs": 20, "output": "Nope"}, "no single output matches"),
])
def test_monte_carlo_errors(client: TestClient, project: Path, body: dict, detail: str) -> None:
    client.post("/api/bowtie/uncertainty", json={"target": "Gas detection", "distribution": "uniform",
                                                 "params": {"min": 0.1, "max": 0.3}})
    head = git.head_sha(project)
    r = client.post("/api/bowtie/monte-carlo", json=body)
    assert r.status_code == 422 and detail in r.json()["detail"]
    assert git.head_sha(project) == head


def test_monte_carlo_needs_a_range(client: TestClient, project: Path) -> None:
    head = git.head_sha(project)
    r = client.post("/api/bowtie/monte-carlo", json={"runs": 20})
    assert r.status_code == 422 and "no input has an uncertainty range" in r.json()["detail"]
    assert git.head_sha(project) == head
