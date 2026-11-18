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
    assert stable_ids == {"cld", "dag", "bn", "fcm", "sd", "theory_of_change", "fault_tree", "bow_tie", "event_tree", "mcda", "ach", "decision_tree", "markov"}
    gsn = next(m for m in data["model_types"] if m["id"] == "gsn")
    assert gsn["can_use_today"] is False
    assert gsn["availability"] == "planned"


def test_capabilities_table_shows_roadmap_status(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = runner.invoke(app, ["capabilities"]).stdout.lower()
    assert "on the roadmap" in out and "not planned" in out


def test_capabilities_json_includes_roadmap(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = json.loads(runner.invoke(app, ["capabilities", "--json"]).stdout)
    by_id = {m["id"]: m["roadmap"] for m in data["model_types"]}
    assert by_id["gsn"] == "roadmap"
    assert by_id["fault_tree"] == "built"
    assert by_id["petri_net"] == "not_planned"


def test_capabilities_surface_manifest(tmp_path: Path, monkeypatch):
    """The surface manifest: what apps built on latris read for each stable model type."""
    from latris.operations.analysis_results import result_surfaces
    from latris.operations.capabilities import SURFACE_MANIFEST_VERSION
    from latris.schema.model_types import list_model_types

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["capabilities", "--surface"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["manifest_version"] == SURFACE_MANIFEST_VERSION
    types = {t["id"]: t for t in data["model_types"]}
    assert set(types) == {s.id for s in list_model_types()}
    for t in types.values():
        assert (t["spec_field"] is None) == (t["spec_schema"] is None)
        if t["registered"]:
            assert t["spec_schema"]["type"] == "object" and t["cli"]
    assert {r["kind"] for t in types.values() for r in t["results"]} == {r.kind for r in result_surfaces()}
    mcda = types["mcda"]["results"][0]
    assert mcda["chart_kinds"] == ["mcda-contributions", "mcda-swing"] and mcda["needs_dataset"] is False
    assert next(r for r in types["dag"]["results"] if r["kind"] == "dag-estimate")["needs_dataset"] is True

    one = json.loads(runner.invoke(app, ["capabilities", "--surface", "-m", "mcda"]).stdout)
    assert [t["id"] for t in one["model_types"]] == ["mcda"]
    assert runner.invoke(app, ["capabilities", "--surface", "-m", "gsn"]).exit_code != 0
