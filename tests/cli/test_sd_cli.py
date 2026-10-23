"""CLI integration tests for the `sd` command group."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from latris.cli.app import app
from tests.conftest import SD_BATHTUB_ROLES

runner = CliRunner()


@pytest.fixture
def diagram(sd_diagram_root, monkeypatch):
    monkeypatch.chdir(sd_diagram_root)
    return sd_diagram_root


@pytest.fixture
def bathtub(sd_bathtub_root, monkeypatch):
    monkeypatch.chdir(sd_bathtub_root)
    return sd_bathtub_root


def _ok(args: list[str]):
    r = runner.invoke(app, ["sd", *args])
    assert r.exit_code == 0, r.stdout
    return r


def test_full_workflow_from_diagram_to_simulation(diagram):
    before = runner.invoke(app, ["sd", "check"])
    assert before.exit_code == 1
    assert "unclassified" in before.stdout

    for label, role in SD_BATHTUB_ROLES:
        _ok(["set-role", label, role])
    _ok(["set-initial-value", "Water", "100", "--units", "liter", "--non-negative"])
    _ok(["set-constant", "Inflow Rate", "5", "-u", "liter/year"])
    _ok(["set-constant", "Drain Rate", "0.1", "-u", "1/year", "--origin", "human-elicited"])
    _ok(["set-equation", "Inflow", "inflow_rate", "-u", "liter/year"])
    _ok(["set-equation", "Outflow", "water * drain_rate", "-u", "liter/year"])

    after = _ok(["check"])
    assert "ready to simulate" in after.stdout


def test_listings(bathtub):
    assert "source_sink" in _ok(["roles"]).stdout
    eqs = _ok(["equations"]).stdout
    assert "water * drain_rate" in eqs and "flow" in eqs
    assert "100" in _ok(["stocks"]).stdout
    assert "1/year" in _ok(["constants"]).stdout
    assert "no tables" in _ok(["tables"]).stdout


def test_equation_errors_are_reported(diagram):
    r = runner.invoke(app, ["sd", "set-equation", "Inflow", "1", "-u", "liter/year"])
    assert r.exit_code != 0
    assert "sd set-role" in r.stdout

    runner.invoke(app, ["sd", "set-role", "Outflow", "flow"])
    r = runner.invoke(app, ["sd", "set-equation", "Outflow", "water * k", "-u", "liter/year"])
    assert r.exit_code != 0
    assert "not a classified SD variable" in r.stdout


def test_check_reports_unit_errors(bathtub):
    _ok(["set-equation", "Inflow", "inflow_rate", "-u", "liter"])
    r = runner.invoke(app, ["sd", "check"])
    assert r.exit_code == 1
    assert "flow_units_incompatible" in r.stdout
    flat = "".join(r.stdout.split()).replace("│", "")  # undo rich's table wrapping
    assert "(liter)/year" in flat


def test_table_round_trip(bathtub):
    # Equations have no unit literals: a unit-bearing number is a named, sourced constant.
    _ok(["set-equation", "Outflow", "water * drain_rate * TABLE(water / water)", "-u", "liter/year"])
    r = runner.invoke(app, ["sd", "check"])
    assert r.exit_code == 1 and "missing_table" in r.stdout

    _ok(["set-table", "Outflow", "-p", "0:0", "-p", "1:0.2", "--x-units", "dimensionless", "--y-units", "dimensionless"])
    assert "(0, 0), (1, 0.2)" in _ok(["tables"]).stdout
    _ok(["check"])


def test_set_table_validates_points(bathtub):
    r = runner.invoke(app, ["sd", "set-table", "Outflow", "-p", "0-1", "--x-units", "dimensionless",
                            "--y-units", "dimensionless"])
    assert r.exit_code != 0


def test_simulate_summary(bathtub):
    pytest.importorskip("scipy")
    r = _ok(["simulate", "--final-time", "20", "--saveper", "5", "--no-record"])
    assert "Water" in r.stdout and "56.7668" in r.stdout  # 50 + 50·e^(−2)
    assert "recorded" not in r.stdout


def test_simulate_json_and_record(bathtub):
    pytest.importorskip("scipy")
    r = _ok(["simulate", "--final-time", "10", "--saveper", "5", "--method", "adaptive", "--json"])
    payload = json.loads(r.stdout)
    assert payload["success"] is True
    assert payload["times"] == [0.0, 5.0, 10.0]
    water = next(i for i, label in payload["labels"].items() if label == "Water")
    assert payload["series"][water][-1] == pytest.approx(50 + 50 * 2.718281828459045**-1, rel=1e-5)
    assert payload["run_id"].startswith("analysis-run_")


def test_simulate_euler_without_scipy_dependency(bathtub):
    r = _ok(["simulate", "--final-time", "1", "--dt", "1", "--method", "euler", "--no-record"])
    assert "forward-euler" in r.stdout


def test_simulate_incomplete_model_fails(diagram):
    r = runner.invoke(app, ["sd", "simulate", "--no-record"])
    assert r.exit_code != 0
    assert "not ready to simulate" in r.stdout
