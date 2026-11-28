"""`latris sd`: settings, scenarios, uncertainty and the analyses — flags, JSON and errors.

The bathtub (conftest ``sd_bathtub_root``): Water fills from Inflow Rate and
drains at Drain Rate; equilibrium 50 L.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from latris.cli.app import app

runner = CliRunner()


@pytest.fixture
def bathtub(sd_bathtub_root, monkeypatch):
    monkeypatch.chdir(sd_bathtub_root)
    return sd_bathtub_root


@pytest.fixture
def diagram(sd_diagram_root, monkeypatch):
    monkeypatch.chdir(sd_diagram_root)
    return sd_diagram_root


def _ok(*args: str) -> str:
    result = runner.invoke(app, ["sd", *args])
    assert result.exit_code == 0, result.output
    return result.output


def _json(*args: str):
    result = runner.invoke(app, ["--json", "sd", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _fails(*args: str) -> str:
    result = runner.invoke(app, ["sd", *args])
    assert result.exit_code != 0, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result.output


def test_empty_listings(diagram) -> None:
    assert "no SD roles" in _ok("roles")
    for cmd in ("equations", "stocks", "constants", "scenarios", "uncertainty"):
        assert "(no" in _ok(cmd).lower() or _ok(cmd).strip(), cmd


def test_json_listings_and_role_edits(bathtub) -> None:
    roles = _json("roles")["result"]
    assert {"node": "Water", "role": "stock", "equation_name": "water"} in roles
    assert any(r["role"] == "source_sink" and r["equation_name"] is None for r in roles)
    for cmd in ("equations", "stocks", "constants", "tables", "settings"):
        assert "result" in _json(cmd), cmd

    payload = _json("set-role", "Tap", "source_sink")
    assert payload["result"]["role"] == "source_sink"
    out = _ok("unset-role", "Drain Rate")
    assert "removed Drain Rate from the simulation" in out
    assert _json("unset-role", "Inflow Rate")["result"]["rows_removed"] >= 1
    assert "error" in _fails("set-role", "Water", "puddle")


def test_settings(bathtub) -> None:
    out = _ok("set-settings", "--time-units", "month", "--initial-time", "0", "--final-time", "24",
              "--dt", "0.5", "--saveper", "1", "--method", "euler")
    assert "month" in out
    shown = _ok("settings")
    assert "24" in shown and "euler" in shown
    assert "error" in _fails("set-settings", "--method", "magic")


def test_simulate_with_what_ifs(bathtub) -> None:
    out = _ok("simulate", "--set", "Drain Rate=0.2", "--final-time", "20", "--dt", "1", "--no-record")
    assert "Water" in out
    out = _ok("simulate", "--apply-to-all", "Inflow Rate=10", "--final-time", "10", "--method", "rk2",
              "--time-units", "year", "--saveper", "2", "--no-record")
    assert "Water" in out
    assert "error" in _fails("simulate", "--set", "Nothing=1", "--no-record")
    assert "error" in _fails("simulate", "--set", "no equals sign", "--no-record")


def test_scenarios_compare_and_remove(bathtub) -> None:
    out = _ok("set-scenario", "Low drain", "--set", "Drain Rate=0.05", "-d", "Slower drain",
              "--reason", "a clogged pipe")
    assert "Low drain" in out
    _ok("set-scenario", "Lower drain", "--set", "Drain Rate=0.02", "--extends", "Low drain",
        "--origin", "human-elicited")
    listed = _ok("scenarios")
    assert "Low drain" in listed and "Lower drain" in listed
    assert any(s["name"] == "Low drain" for s in _json("scenarios")["result"])

    out = _ok("simulate", "-s", "Low drain", "--final-time", "20", "--no-record")
    assert "Low drain" in out

    _ok("set-uncertainty", "Inflow Rate", "uniform", "--min", "4", "--max", "6")
    out = _ok("compare", "Water", "-s", "Low drain", "-s", "Lower drain", "--runs", "4", "--final-time", "10",
              "--dt", "1", "--no-record")
    assert "Low drain" in out
    payload = _json("compare", "Water", "-s", "Low drain", "--runs", "4", "--final-time", "10", "--dt", "1",
                    "--metric", "peak", "-r", "baseline", "--method", "euler", "--no-record")
    assert payload["result"]

    assert "error" in _fails("set-scenario", "Broken", "--set", "Drain Rate=0.1", "--extends", "Nope")
    # Removing a scenario another one extends is refused; leaf first, then the base.
    _fails("remove-scenario", "Low drain")
    assert "removed" in _ok("remove-scenario", "Lower drain")
    assert "removed" in _ok("remove-scenario", "Low drain")
    assert "error" in _fails("remove-scenario", "Low drain")


def test_uncertainty_monte_carlo_and_sensitivity(bathtub) -> None:
    assert "error" in _fails("set-uncertainty", "Drain Rate", "uniform")  # no bounds
    _ok("set-uncertainty", "Drain Rate", "uniform", "--min", "0.05", "--max", "0.15", "--reason", "inventory")
    _ok("set-uncertainty", "Inflow Rate", "triangular", "--min", "4", "--mode", "5", "--max", "6")
    _ok("set-uncertainty", "Water", "normal", "--mean", "100", "--sd", "5")
    listed = _ok("uncertainty")
    assert "uniform" in listed and "triangular" in listed and "normal" in listed
    assert len(_json("uncertainty")["result"]) == 3

    out = _ok("monte-carlo", "--runs", "6", "--seed", "7", "--final-time", "10", "--dt", "1", "-v", "Water",
              "--sampling", "random", "--no-record")
    assert "Water" in out
    payload = _json("monte-carlo", "--runs", "4", "--final-time", "5", "--dt", "1", "--method", "euler",
                    "--saveper", "1", "--no-record")
    assert payload["result"]
    assert "error" in _fails("monte-carlo", "--runs", "1", "--no-record")

    out = _ok("sensitivity", "Water", "--final-time", "10", "--dt", "1", "--top", "2", "--pct", "20", "--no-record")
    assert "Drain Rate" in out or "Inflow Rate" in out
    payload = _json("sensitivity", "Water", "--metric", "peak", "--final-time", "5", "--dt", "1",
                    "--method", "euler", "--no-record")
    assert payload["result"]
    assert "error" in _fails("sensitivity", "Water", "--metric", "loudest", "--no-record")

    assert "cleared" in _ok("clear-uncertainty", "Water").lower()
    assert "error" in _fails("clear-uncertainty", "Water")


def test_recorded_runs(bathtub) -> None:
    _ok("set-uncertainty", "Drain Rate", "uniform", "--min", "0.05", "--max", "0.15")
    assert "recorded" in _ok("monte-carlo", "--runs", "4", "--final-time", "5", "--dt", "1")
    assert "recorded" in _ok("sensitivity", "Water", "--final-time", "5", "--dt", "1")


def test_loops(bathtub) -> None:
    out = _ok("loops", "--final-time", "10", "--dt", "1", "--no-record")
    assert out.strip()
    payload = _json("loops", "--final-time", "10", "--dt", "1", "--from", "0", "--to", "5", "--method", "euler",
                    "--no-record")
    assert "loops" in payload["result"]
