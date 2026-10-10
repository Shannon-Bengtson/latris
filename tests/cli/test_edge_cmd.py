"""CLI tests for the `edge` command group: add, list, remove."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import edges as edge_ops

runner = CliRunner()


def test_edge_list_empty(empty_project_root: Path, monkeypatch):
    monkeypatch.chdir(empty_project_root)
    r = runner.invoke(app, ["edge", "list"])
    assert r.exit_code == 0, r.output
    assert "no edges yet" in r.output


def test_edge_list_with_edges(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["edge", "list"])
    assert r.exit_code == 0, r.output
    assert "Price" in r.output
    assert "Demand" in r.output
    assert "causal" in r.output


def test_edge_add_happy(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    # Add a back-edge Demand -> Price with a non-default kind.
    r = runner.invoke(app, ["edge", "add", "Demand", "Price", "--kind", "temporal"])
    assert r.exit_code == 0, r.output
    assert "added" in r.output
    assert "temporal" in r.output
    edges = edge_ops.list_edges(root=two_node_project_root)
    assert any(e.kind == "temporal" for e in edges)


def test_edge_add_unknown_node_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["edge", "add", "Nonexistent", "Demand"])
    assert r.exit_code == 1
    assert "error:" in r.output


def test_edge_add_self_loop_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["edge", "add", "Price", "Price"])
    # self-loop raises ValueError -> exit code 2.
    assert r.exit_code == 2
    assert "self-loop" in r.output


def test_edge_remove_happy(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    edge = edge_ops.list_edges(root=two_node_project_root)[0]
    r = runner.invoke(app, ["edge", "remove", edge.id])
    assert r.exit_code == 0, r.output
    assert "removed" in r.output
    assert edge_ops.list_edges(root=two_node_project_root) == []


def test_edge_remove_unknown_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["edge", "remove", "edge_doesnotexist"])
    assert r.exit_code == 1
    assert "error:" in r.output


def test_edge_list_outside_project_errors(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["edge", "list"])
    assert r.exit_code == 1
    assert "error:" in r.output
