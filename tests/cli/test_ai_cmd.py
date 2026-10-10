"""Tests for the `latris ai` CLI surface.

Focused on the generic dispatcher `ai call run <prompt>` added to
support scripting any prompt without a dedicated subcommand. Uses
LATRIS_AI_MOCK=1 so no real LLM is hit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.ai.proposals import SuggestedVariable, SuggestedVariablesResult
from latris.cli.ai_cmd import app as ai_app
from latris.operations.init import init_project


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")


@pytest.fixture(autouse=True)
def _clean_mock():
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Does X cause Y?")
    monkeypatch.chdir(root)
    return root


def _register_suggest_variables_mock() -> None:
    mock = MockAdapter.shared()
    result = ChatResult(
        parsed=SuggestedVariablesResult(
            variables=[
                SuggestedVariable(label="Hours worked", kind="variable", description="Weekly hours."),
                SuggestedVariable(label="Output quality", kind="variable", description="Quality of work."),
            ]
        ),
        raw="…",
        model_id="mock-model",
        token_usage={"input_tokens": 50, "output_tokens": 30},
        cost_usd=0.001,
    )
    mock.register_default(response_cls=SuggestedVariablesResult, result=result)


class TestCallRun:
    def test_dispatches_known_prompt(self, project: Path) -> None:
        _register_suggest_variables_mock()
        runner = CliRunner()
        r = runner.invoke(
            ai_app,
            ["call", "run", "SuggestVariables", "--inputs", '{"focus": "work hours"}', "--yes"],
        )
        assert r.exit_code == 0, r.output + (r.stderr or "")
        # Read-only prompt prints rendered output (generic JSON fallback).
        assert "Hours worked" in r.output
        assert "approved" in r.output

    def test_default_inputs(self, project: Path) -> None:
        """No --inputs argument means an empty dict, not an error."""
        _register_suggest_variables_mock()
        runner = CliRunner()
        r = runner.invoke(ai_app, ["call", "run", "SuggestVariables", "--yes"])
        assert r.exit_code == 0, r.output + (r.stderr or "")

    def test_unknown_prompt(self, project: Path) -> None:
        runner = CliRunner()
        r = runner.invoke(ai_app, ["call", "run", "NotAPromptName"])
        assert r.exit_code != 0
        combined = r.output + (r.stderr or "")
        assert "unknown prompt" in combined.lower() or "NotAPromptName" in combined

    def test_invalid_json_inputs(self, project: Path) -> None:
        runner = CliRunner()
        r = runner.invoke(
            ai_app,
            ["call", "run", "SuggestVariables", "--inputs", "{not json"],
        )
        assert r.exit_code != 0
        combined = r.output + (r.stderr or "")
        assert "JSON" in combined or "json" in combined

    def test_inputs_must_be_object(self, project: Path) -> None:
        runner = CliRunner()
        r = runner.invoke(
            ai_app,
            ["call", "run", "SuggestVariables", "--inputs", "[1,2,3]"],
        )
        assert r.exit_code != 0
        combined = r.output + (r.stderr or "")
        assert "object" in combined.lower()
