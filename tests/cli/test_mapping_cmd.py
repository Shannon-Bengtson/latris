"""CLI tests for the `mapping` command group: add, remove, list, approve."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import mappings as mapping_ops

runner = CliRunner()


def test_mapping_list_empty(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["mapping", "list"])
    assert r.exit_code == 0, r.output
    assert "no mappings" in r.output


def test_mapping_add_happy(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["mapping", "add", "Price", "cld"])
    assert r.exit_code == 0, r.output
    assert "Mapped" in r.output
    assert mapping_ops.list_mappings(root=two_node_project_root)


def test_mapping_add_duplicate_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["mapping", "add", "Price", "cld"])
    r = runner.invoke(app, ["mapping", "add", "Price", "cld"])
    assert r.exit_code == 2
    assert "already mapped" in r.output


def test_mapping_list_shows_rows_and_filters(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["mapping", "add", "Price", "cld"])
    runner.invoke(app, ["mapping", "add", "Demand", "dag"])

    r = runner.invoke(app, ["mapping", "list"])
    assert r.exit_code == 0, r.output
    assert "cld" in r.output
    assert "dag" in r.output

    # Filtered view: only cld rows.
    r2 = runner.invoke(app, ["mapping", "list", "--view", "dag"])
    assert r2.exit_code == 0, r2.output
    assert "dag" in r2.output
    assert "cld" not in r2.output


def test_mapping_remove_happy(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["mapping", "add", "Price", "cld"])
    r = runner.invoke(app, ["mapping", "remove", "Price", "cld"])
    assert r.exit_code == 0, r.output
    assert "Unmapped" in r.output
    assert mapping_ops.list_mappings(root=two_node_project_root) == []


def test_mapping_remove_not_mapped_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["mapping", "remove", "Price", "cld"])
    assert r.exit_code == 2
    assert "not mapped" in r.output


def test_mapping_approve_happy(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    runner.invoke(app, ["mapping", "add", "Price", "cld", "--ai-proposed"])
    r = runner.invoke(app, ["mapping", "approve", "Price", "cld"])
    assert r.exit_code == 0, r.output
    assert "Approved" in r.output
    m = mapping_ops.list_mappings(root=two_node_project_root)[0]
    assert m.maturity == "approved"


def test_mapping_approve_missing_errors(two_node_project_root: Path, monkeypatch):
    monkeypatch.chdir(two_node_project_root)
    r = runner.invoke(app, ["mapping", "approve", "Price", "cld"])
    assert r.exit_code == 2
    assert "No mapping found" in r.output


def test_mapping_outside_project_errors(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["mapping", "list"])
    assert r.exit_code == 1
    assert "error:" in r.output
