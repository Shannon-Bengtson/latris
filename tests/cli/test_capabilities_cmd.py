"""Tests for ``latris capabilities``."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app

runner = CliRunner()


def test_capabilities_outside_project(tmp_path: Path, monkeypatch):
    # The whole point: registry-only, works with no project at all.
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["capabilities"])
    assert result.exit_code == 0
    assert "cld" in result.stdout.lower()
    assert "theory of change" in result.stdout.lower()


def test_capabilities_json_shape(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["capabilities", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "model_types" in data
    assert "excluded_by_design" in data
    stable_ids = {m["id"] for m in data["model_types"] if m["can_use_today"]}
    assert stable_ids == {"cld", "dag", "bn", "fcm", "sd"}
    toc = next(m for m in data["model_types"] if m["id"] == "theory_of_change")
    assert toc["can_use_today"] is False
    assert toc["availability"] == "planned"


def test_capabilities_table_shows_roadmap_status(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = runner.invoke(app, ["capabilities"]).stdout.lower()
    assert "on the roadmap" in out and "parked" in out and "not planned" in out


def test_capabilities_json_includes_roadmap(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = json.loads(runner.invoke(app, ["capabilities", "--json"]).stdout)
    by_id = {m["id"]: m["roadmap"] for m in data["model_types"]}
    assert by_id["fault_tree"] == "roadmap"
    assert by_id["petri_net"] == "not_planned"
