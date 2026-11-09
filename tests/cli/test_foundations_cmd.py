"""Tests for ``latris foundations`` and the ``foundations`` docs topic."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app

runner = CliRunner()


def test_foundations_outside_project(tmp_path: Path, monkeypatch):
    # Registry-only, like `latris capabilities`: no project needed.
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["foundations"])
    assert result.exit_code == 0
    assert "cld-loop-analysis" in result.stdout
    assert "evidence-source-check" in result.stdout
    # Cell-leading citation text survives the narrow test terminal's wrapping.
    assert "Sterman (2000)" in result.stdout


def test_foundations_json_shape(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["foundations", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 11
    by_id = {f["id"]: f for f in data}
    assert set(by_id) >= {"cld-loop-analysis", "sd-loop-dominance", "evidence-source-check", "bn-psa"}
    assert by_id["evidence-source-check"]["applies_to"] == ["*"]
    entry = by_id["sd-simulation"]
    assert entry["method"] and entry["citation"] and entry["used_for"] and entry["limits"]


def test_docs_foundations_topic():
    result = runner.invoke(app, ["docs", "foundations"])
    assert result.exit_code == 0
    assert result.output.startswith("# Methods and foundations")
    assert "Schoenberg" in result.output
