"""`latris ai`: prompts, interactions, keys, config, and the interactive call paths.

Hermetic: the mock AI (``LATRIS_AI_MOCK=1``) and an in-memory keyring, so no
model and no real OS keyring is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import keyring
import keyring.backend
import keyring.errors
import pytest
from typer.testing import CliRunner

from latris.ai import interactions as inter_ops
from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.ai.adapters.mock_fixtures import register_gui_defaults
from latris.ai.proposals import EdgeProposal, NewConnectionsProposal
from latris.cli.app import app
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import Substrate

runner = CliRunner()


class _MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError(username)
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    register_gui_defaults()
    previous = keyring.get_keyring()
    memory = _MemoryKeyring()
    keyring.set_keyring(memory)
    yield memory
    keyring.set_keyring(previous)
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    monkeypatch.chdir(root)
    return root


def _substrate(root: Path) -> Substrate:
    return load_model(Substrate, ProjectPaths(root).conceptual_yaml)


# ── prompts ─────────────────────────────────────────────────────────────


def test_prompts_list_and_show(project: Path) -> None:
    out = runner.invoke(app, ["ai", "prompts", "list"]).output
    assert "ExplainThisElement" in out
    assert "prompts registered" in out
    out = runner.invoke(app, ["ai", "prompts", "show", "ChallengeThisConnection"]).output
    assert "Inputs:" in out and "target_id" in out and "(default: None)" in out
    assert "Template:" in out and "Expected output:" in out
    result = runner.invoke(app, ["ai", "prompts", "show", "NoSuchPrompt"])
    assert result.exit_code == 1


# ── interactions ────────────────────────────────────────────────────────


def test_interactions_empty_and_bad_filter(project: Path) -> None:
    assert "no interactions recorded yet" in runner.invoke(app, ["ai", "interactions", "list"]).output
    result = runner.invoke(app, ["ai", "interactions", "list", "--adoption", "maybe"])
    assert result.exit_code == 2
    result = runner.invoke(app, ["ai", "interactions", "show", "interaction_nope"])
    assert result.exit_code == 2
    assert "no interaction matches" in result.output


def test_interactions_list_and_show(project: Path, monkeypatch) -> None:
    from latris.cli import ai_cmd

    monkeypatch.setattr(ai_cmd.console, "width", 250)  # so the table doesn't truncate
    node, _ = add_node("Price", root=project)
    assert runner.invoke(app, ["ai", "call", "explain", "Price"]).exit_code == 0
    inter_ops.record_interaction(
        prompt_name="ScopeCheck",
        prompt_inputs={},
        model_id="mock-model",
        response_summary="x" * 80,
        adoption="failed",
        error_class="LLMCallError",
        error_message="boom",
        root=project,
    )

    out = runner.invoke(app, ["ai", "interactions", "list"]).output
    assert "ExplainThisElement" in out and "ScopeCheck" in out
    assert "failed" in out
    out = runner.invoke(app, ["ai", "interactions", "list", "-p", "ScopeCheck", "--adoption", "failed", "-n", "1"])
    assert "ExplainThisElement" not in out.output
    out = runner.invoke(app, ["ai", "interactions", "list", "-t", node.id]).output
    assert "ExplainThisElement" in out and "ScopeCheck" not in out

    explain = inter_ops.list_interactions(prompt_name="ExplainThisElement", root=project)[0]
    out = runner.invoke(app, ["ai", "interactions", "show", explain.id]).output
    assert f"id: {explain.id}" in out
    assert f"target_ids: {node.id}" in out
    assert "summary:" in out
    assert "inputs:" in out


# ── keys ────────────────────────────────────────────────────────────────


def test_keys_set_list_unset(project: Path, _offline: _MemoryKeyring, monkeypatch) -> None:
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert "no keys configured" in runner.invoke(app, ["ai", "key", "list"]).output

    result = runner.invoke(app, ["ai", "key", "set", "anthropic"], input="   \n")
    assert result.exit_code == 2
    assert "refusing to store empty key" in result.output

    result = runner.invoke(app, ["ai", "key", "set", "anthropic"], input="sk-test-value\n")
    assert result.exit_code == 0, result.output
    assert "stored key for anthropic" in result.output
    assert "sk-test-value" not in result.output
    assert ("latris-sync", "anthropic") in _offline.store or any(k[1] == "anthropic" for k in _offline.store)

    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    out = runner.invoke(app, ["ai", "key", "list"]).output
    assert "anthropic" in out and "keyring" in out
    assert "openai" in out and "env" in out
    assert "from-env" not in out and "sk-test-value" not in out

    assert "removed key for anthropic" in runner.invoke(app, ["ai", "key", "unset", "anthropic"]).output
    assert "no keyring entry" in runner.invoke(app, ["ai", "key", "unset", "anthropic"]).output


# ── config ──────────────────────────────────────────────────────────────


def test_config_show_and_set(project: Path) -> None:
    out = runner.invoke(app, ["ai", "config", "show"]).output
    assert "default_model" in out and "using built-in defaults" in out

    result = runner.invoke(app, ["ai", "config", "set", "temperature", "0.1"])
    assert result.exit_code == 0, result.output
    assert "wrote temperature = 0.1" in result.output
    assert runner.invoke(app, ["ai", "config", "set", "max_tokens", "900"]).exit_code == 0
    assert runner.invoke(app, ["ai", "config", "set", "default_model", "mock/model"]).exit_code == 0
    out = runner.invoke(app, ["ai", "config", "show"]).output
    assert "source:" in out and "900" in out

    result = runner.invoke(app, ["ai", "config", "set", "colour", "blue"])
    assert result.exit_code == 2
    assert "unknown config key" in result.output
    result = runner.invoke(app, ["ai", "config", "set", "temperature", "warm"])
    assert result.exit_code == 2


# ── call: confirmation paths ────────────────────────────────────────────


def test_call_dry_run(project: Path) -> None:
    add_node("Price", root=project)
    result = runner.invoke(app, ["ai", "call", "explain", "Price", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert inter_ops.list_interactions(root=project) == []
    result = runner.invoke(app, ["ai", "call", "draft", "Demand", "--dry-run", "-b", "a2020, b2021"])
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    result = runner.invoke(app, ["ai", "call", "find-connections", "--dry-run"])
    assert result.exit_code == 0, result.output


def test_call_rejected_at_the_prompt_records_a_reason(project: Path) -> None:
    add_node("Price", root=project)
    result = runner.invoke(app, ["ai", "call", "challenge", "Price"], input="n\nwrong-fact\n")
    assert result.exit_code == 0, result.output
    assert "Apply this proposal?" in result.output
    assert "rejected" in result.output
    (record,) = inter_ops.list_interactions(root=project)
    assert record.adoption == "rejected"
    assert record.rejection_reason == "wrong-fact"


@pytest.mark.parametrize(("answer", "adopted"), [("none", False), ("9", False), ("x", False), ("0", True)])
def test_draft_pick(project: Path, answer: str, adopted: bool) -> None:
    result = runner.invoke(app, ["ai", "call", "draft", "Demand"], input=f"{answer}\n")
    assert result.exit_code == 0, result.output
    assert "Candidate framings:" in result.output
    if adopted:
        assert "approved" in result.output
        assert _substrate(project).entities
    else:
        assert "rejected" in result.output
        assert not _substrate(project).entities
    if answer == "9":
        assert "out of range" in result.output
    if answer == "x":
        assert "Invalid input" in result.output


def test_draft_yes(project: Path) -> None:
    result = runner.invoke(app, ["ai", "call", "draft", "Demand", "--yes"])
    assert result.exit_code == 0, result.output
    assert "approved" in result.output
    assert "applied" in result.output


def _connections(*proposals: EdgeProposal) -> None:
    MockAdapter.shared().register_default(
        response_cls=NewConnectionsProposal,
        result=ChatResult(parsed=NewConnectionsProposal(proposals=list(proposals)), raw="(mock)", model_id="mock"),
    )


def test_find_connections_paths(project: Path) -> None:
    a, _ = add_node("Price", root=project)
    b, _ = add_node("Demand", root=project)

    _connections()
    result = runner.invoke(app, ["ai", "call", "find-connections", "--yes"])
    assert "rejected" in result.output  # nothing to apply: --yes is a no-op
    result = runner.invoke(app, ["ai", "call", "find-connections"], input="\n")
    assert "rejected" in result.output

    _connections(EdgeProposal(from_id=a.id, to_id=b.id, description="price sets demand"))
    result = runner.invoke(app, ["ai", "call", "find-connections"], input="none\n")
    assert "rejected" in result.output
    result = runner.invoke(app, ["ai", "call", "find-connections", "-f", a.id], input="zero\n")
    assert "Invalid input" in result.output
    assert not _substrate(project).edges

    result = runner.invoke(app, ["ai", "call", "find-connections"], input="0\n")
    assert result.exit_code == 0, result.output
    assert "approved" in result.output
    assert len(_substrate(project).edges) == 1


# ── call run / task ─────────────────────────────────────────────────────


def test_call_run_bad_inputs(project: Path) -> None:
    result = runner.invoke(app, ["ai", "call", "run", "ScopeCheck", "--inputs", "{nope"])
    assert result.exit_code == 2
    result = runner.invoke(app, ["ai", "call", "run", "ScopeCheck", "--inputs", "[1]"])
    assert result.exit_code == 2
    result = runner.invoke(app, ["ai", "call", "run", "ProjectToFormalView", "--inputs", '{"view": "nope"}'])
    assert result.exit_code == 2
    assert "view" in result.output


def test_task_emit_and_errors(project: Path, tmp_path: Path) -> None:
    add_node("Price", root=project)
    out_file = tmp_path / "task.json"
    result = runner.invoke(
        app, ["ai", "task", "emit", "ExplainThisElement", "-i", '{"target_id": "Price"}', "-o", str(out_file)]
    )
    assert result.exit_code == 0, result.output
    assert "task written" in result.output
    assert json.loads(out_file.read_text())["prompt_name"] == "ExplainThisElement"

    for inputs in ("{bad", "[]"):
        result = runner.invoke(app, ["ai", "task", "emit", "ExplainThisElement", "-i", inputs])
        assert result.exit_code == 2
    result = runner.invoke(app, ["ai", "task", "emit", "NoSuchPrompt"])
    assert result.exit_code == 2

    bad_task = tmp_path / "bad.json"
    bad_task.write_text('{"inputs": {}}')
    result = runner.invoke(app, ["ai", "task", "apply", "--task", str(bad_task), "--from", str(bad_task)])
    assert result.exit_code == 2
    assert "prompt_name" in result.output

    result = runner.invoke(app, ["ai", "task", "apply", "--task", str(tmp_path / "gone.json"), "--from", "x"])
    assert result.exit_code == 1
    assert "error" in result.output
