"""`latris completeness`: the gate's output, the record transitions, and their errors."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.ai.proposals import CompletenessGateResult, MissingVariableProposal
from latris.cli.app import app
from latris.operations.completeness import load_report
from latris.operations.init import init_project

runner = CliRunner()


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    monkeypatch.chdir(root)
    return root


def _gate_returns(*entries: MissingVariableProposal) -> None:
    MockAdapter.shared().register_default(
        response_cls=CompletenessGateResult,
        result=ChatResult(
            parsed=CompletenessGateResult(model_type="cld", coverage_ratio=0.5, entries=list(entries)),
            raw="(mock)",
            model_id="mock-model",
        ),
    )


def _mv(name: str, severity: str = "required") -> MissingVariableProposal:
    return MissingVariableProposal(name=name, rationale="needed", severity=severity, confidence="high")


def _ids(root: Path) -> dict[str, str]:
    return {mv.name: mv.id for mv in load_report("cld", root=root).entries}


def test_check_with_nothing_missing(project: Path) -> None:
    _gate_returns()
    result = runner.invoke(app, ["completeness", "check"])
    assert result.exit_code == 0, result.output
    assert "no missing-variable records for cld" in result.output


def test_check_lists_entries_and_counts(project: Path) -> None:
    _gate_returns(_mv("Income"))
    result = runner.invoke(app, ["completeness", "check", "cld", "--claim", "Demand falls"])
    assert result.exit_code == 0, result.output
    assert "Income" in result.output
    assert "1 entry" in result.output

    _gate_returns(_mv("Income"), _mv("Season", "optional"))
    result = runner.invoke(app, ["completeness", "check", "cld"])
    assert "2 entries" in result.output


def test_list_and_transitions(project: Path) -> None:
    _gate_returns(_mv("Income"), _mv("Season", "optional"), _mv("Weather", "recommended"))
    assert runner.invoke(app, ["completeness", "check", "cld"]).exit_code == 0
    ids = _ids(project)

    listed = runner.invoke(app, ["completeness", "list"])
    assert listed.exit_code == 0
    for name in ids:
        assert name in listed.output

    result = runner.invoke(app, ["completeness", "override", "cld", ids["Income"], "--rationale", "out of scope"])
    assert result.exit_code == 0, result.output
    assert "overrode" in result.output
    assert "linked Exclusion exclusion_" in result.output

    result = runner.invoke(app, ["completeness", "dismiss", "cld", ids["Season"]])
    assert result.exit_code == 0, result.output
    assert "dismissed" in result.output

    result = runner.invoke(app, ["completeness", "mark-added", "cld", ids["Weather"], "--entity-id", "node_x"])
    assert result.exit_code == 0, result.output
    assert "marked added" in result.output
    assert "(entity node_x)" in result.output

    still_open = runner.invoke(app, ["completeness", "list", "cld", "--disposition", "open"])
    assert "no records match" in still_open.output
    excluded = runner.invoke(app, ["completeness", "list", "cld", "--disposition", "excluded"])
    assert "Income" in excluded.output
    assert "Season" not in excluded.output


def test_list_with_no_report(project: Path) -> None:
    result = runner.invoke(app, ["completeness", "list"])
    assert result.exit_code == 0
    assert "no records match" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["override", "cld", "missing_nope", "--rationale", "x"],
        ["dismiss", "cld", "missing_nope"],
        ["mark-added", "cld", "missing_nope", "--entity-id", "node_x"],
    ],
)
def test_unknown_record_is_refused(project: Path, args: list[str]) -> None:
    result = runner.invoke(app, ["completeness", *args])
    assert result.exit_code == 2
    assert "no missing-variable 'missing_nope'" in result.output


def test_required_options(project: Path) -> None:
    assert runner.invoke(app, ["completeness", "override", "cld", "x"]).exit_code == 2
    assert runner.invoke(app, ["completeness", "mark-added", "cld", "x"]).exit_code == 2
