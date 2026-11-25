"""Undo and redo step through a person's actions; history only ever grows."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import history as history_ops
from latris.operations import nodes as node_ops
from latris.operations import views as view_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="Test")
    return root


def _labels(root: Path) -> set[str]:
    return {n.label for n in node_ops.list_nodes(root=root)}


def _count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout)


def test_each_undo_steps_one_action_further_back(project: Path) -> None:
    for label in ("A", "B", "C"):
        node_ops.add_node(label, root=project)
    history_ops.undo(project)
    assert _labels(project) == {"A", "B"}
    history_ops.undo(project)
    assert _labels(project) == {"A"}
    history_ops.undo(project)
    assert _labels(project) == set()


def test_redo_puts_actions_back_in_order_and_undo_takes_them_away_again(project: Path) -> None:
    node_ops.add_node("A", root=project)
    node_ops.add_node("B", root=project)
    history_ops.undo(project)
    history_ops.undo(project)
    _, subject = history_ops.redo(project)
    assert "A" in subject and _labels(project) == {"A"}
    history_ops.redo(project)
    assert _labels(project) == {"A", "B"}
    with pytest.raises(history_ops.NothingToUndo):
        history_ops.redo(project)
    history_ops.undo(project)
    assert _labels(project) == {"A"}
    history_ops.undo(project)
    assert _labels(project) == set()


def test_a_new_action_leaves_nothing_to_redo(project: Path) -> None:
    node_ops.add_node("A", root=project)
    history_ops.undo(project)
    node_ops.add_node("B", root=project)
    assert history_ops.status(project).redo is None
    with pytest.raises(history_ops.NothingToUndo):
        history_ops.redo(project)
    history_ops.undo(project)
    assert _labels(project) == set()


def test_history_only_grows(project: Path) -> None:
    node_ops.add_node("A", root=project)
    before = _count(project)
    history_ops.undo(project)
    history_ops.redo(project)
    assert _count(project) == before + 2
    subjects = git.run_git(["log", "-2", "--format=%s"], cwd=project).stdout.splitlines()
    assert subjects[0].startswith("Redo: ") and subjects[1].startswith("Undo: ")


def test_bookkeeping_is_undone_with_the_action_it_followed(project: Path) -> None:
    """Opening a model type maps the model into it and re-projects: undo must still take the factor away."""
    node_ops.add_node("A", root=project)
    node_ops.add_node("B", root=project)
    view_ops.auto_project("cld", root=project)  # what the app does when Build opens
    last = git.run_git(["log", "-1", "--format=%B"], cwd=project).stdout
    assert "Bookkeeping: derived" in last
    assert history_ops.status(project).undo == 'Added node "B" (concept)'
    history_ops.undo(project)
    assert _labels(project) == {"A"}
    view_ops.auto_project("cld", root=project)
    history_ops.undo(project)
    assert _labels(project) == set()
    history_ops.redo(project)
    assert _labels(project) == {"A"}


def test_undo_stops_at_the_start(project: Path) -> None:
    while history_ops.status(project).undo is not None:  # whatever init committed after the first commit
        history_ops.undo(project)
    with pytest.raises(history_ops.NothingToUndo):
        history_ops.undo(project)


def test_routes(project: Path) -> None:
    client = TestClient(create_app(project_root=project))
    client.post("/api/nodes", json={"label": "A"})
    client.post("/api/nodes", json={"label": "B"})
    assert "B" in client.get("/api/history").json()["undo"]
    r = client.post("/api/history/undo")
    assert r.status_code == 200 and "B" in r.json()["action"] and "B" in r.json()["redo"]
    assert client.post("/api/history/undo").status_code == 200
    assert [n["label"] for n in client.get("/api/nodes").json()] == []
    assert client.post("/api/history/redo").status_code == 200
    assert client.post("/api/history/redo").status_code == 200
    r = client.post("/api/history/redo")
    assert r.status_code == 409 and r.json()["detail"] == "Nothing to redo."
    assert sorted(n["label"] for n in client.get("/api/nodes").json()) == ["A", "B"]
