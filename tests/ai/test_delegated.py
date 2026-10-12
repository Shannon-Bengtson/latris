"""End-to-end tests for delegated (bring-your-own-agent) AI calls.

The external agent's answer is a hand-written JSON file — no adapter is
involved, so these tests never register a MockAdapter response: passing
proves the delegated path never touches the adapter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.ai import interactions as inter_ops
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.cli.app import app
from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo import git


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
    attr_ops.set_attribute(a.id, "description", "Posted retail price.", root=root)
    monkeypatch.chdir(root)
    return root, a, b, edge


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


def _write_agent_response(root: Path, payload: dict) -> Path:
    path = root / "agent-response.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------- emit ----------


def test_emit_task_package_fields_and_no_side_effects(project) -> None:
    root, a, _, _ = project
    before = _commit_count(root)
    result = CliRunner().invoke(
        app,
        ["ai", "task", "emit", "ExplainThisElement", "--inputs", json.dumps({"target_id": a.id})],
    )
    assert result.exit_code == 0, result.output
    package = json.loads(result.output)
    assert package["task_version"] == 1
    assert package["prompt_name"] == "ExplainThisElement"
    assert package["title"]
    assert package["intent"] == "insight"
    assert package["scope"] == "element"
    assert package["inputs"] == {"target_id": a.id}
    assert package["system"]
    assert package["user"]
    schema = package["response_schema"]
    assert "explanation" in schema["properties"]
    assert "explanation" in schema["required"]
    assert "latris ai task apply" in package["instructions"]

    # Nothing written: no interaction, no commit.
    assert inter_ops.list_interactions(root=root) == []
    assert _commit_count(root) == before


def test_emit_unknown_prompt_rejected(project) -> None:
    root, *_ = project
    result = CliRunner().invoke(app, ["ai", "task", "emit", "NoSuchPrompt"])
    assert result.exit_code != 0


# ---------- apply (mutating) ----------


def test_apply_mutating_happy_path(project) -> None:
    root, _, _, edge = project
    task_path = root / "task.json"
    result = CliRunner().invoke(
        app,
        ["ai", "task", "emit", "ChallengeThisConnection",
         "--inputs", json.dumps({"target_id": edge.id, "target_attribute": "polarity"}),
         "--output", str(task_path)],
    )
    assert result.exit_code == 0, result.output
    response_path = _write_agent_response(root, {
        "target_id": edge.id,
        "target_attribute": "polarity",
        "argument": "Reverse causality may run from demand to price.",
        "opening_turn": "Consider the simultaneity bias in retail data.",
        "recommended_state": "retained-with-caveat",
    })

    before = _commit_count(root)
    result = CliRunner().invoke(
        app,
        ["ai", "task", "apply", "--task", str(task_path), "--from", str(response_path), "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()
    assert "external-agent" in result.output
    # Same commit contract as the equivalent `ai call` test.
    assert _commit_count(root) > before + 1

    from latris.operations import challenges as ch_ops

    challenges = ch_ops.list_challenges(root=root)
    assert len(challenges) == 1
    assert challenges[0].argument.startswith("Reverse")

    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    rec = records[0]
    assert rec.prompt_name == "ChallengeThisConnection"
    assert rec.adoption == "approved"
    assert rec.model_id == "external-agent"
    assert rec.token_usage == {}
    assert rec.cost_usd is None
    assert rec.approved_by and rec.approved_by.name == "Test Runner"
    assert rec.proposal_ids  # the created challenge id
    assert "Reverse causality" in (rec.response_full or "")


def test_apply_rejected_via_stdin_no_mutation(project) -> None:
    root, _, _, edge = project
    task_path = root / "task.json"
    result = CliRunner().invoke(
        app,
        ["ai", "task", "emit", "ChallengeThisConnection",
         "--inputs", json.dumps({"target_id": edge.id, "target_attribute": "polarity"}),
         "--output", str(task_path)],
    )
    assert result.exit_code == 0, result.output
    response_path = _write_agent_response(root, {
        "target_id": edge.id,
        "target_attribute": "polarity",
        "argument": "Weak argument.",
        "opening_turn": None,
        "recommended_state": None,
    })

    # No --yes: answer "n" at the confirm gate.
    result = CliRunner().invoke(
        app,
        ["ai", "task", "apply", "--task", str(task_path), "--from", str(response_path)],
        input="n\n",
    )
    assert result.exit_code == 0, result.output
    assert "rejected" in result.output.lower()

    from latris.operations import challenges as ch_ops

    assert ch_ops.list_challenges(root=root) == []  # no mutation

    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    assert records[0].adoption == "rejected"
    assert records[0].model_id == "external-agent"


# ---------- apply (read-only) ----------


def test_apply_read_only_approved_without_confirm(project) -> None:
    root, a, _, _ = project
    task_path = root / "task.json"
    result = CliRunner().invoke(
        app,
        ["ai", "task", "emit", "ExplainThisElement",
         "--inputs", json.dumps({"target_id": a.id}),
         "--output", str(task_path)],
    )
    assert result.exit_code == 0, result.output
    response_path = _write_agent_response(root, {
        "explanation": "Price is a driver node in the causal framing.",
        "referenced_ids": [a.id],
    })

    # No --yes and empty stdin: read-only prompts skip the confirm gate.
    result = CliRunner().invoke(
        app,
        ["ai", "task", "apply", "--task", str(task_path), "--from", str(response_path)],
    )
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()
    assert "driver node" in result.output  # rendered prose printed

    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    assert records[0].adoption == "approved"
    assert records[0].model_id == "external-agent"
    assert records[0].approved_by and records[0].approved_by.name == "Test Runner"


# ---------- apply (failure paths) ----------


def test_apply_invalid_response_logged_as_failed(project) -> None:
    root, a, _, _ = project
    task_path = root / "task.json"
    result = CliRunner().invoke(
        app,
        ["ai", "task", "emit", "ExplainThisElement",
         "--inputs", json.dumps({"target_id": a.id}),
         "--output", str(task_path)],
    )
    assert result.exit_code == 0, result.output
    # Valid JSON, but not the schema the prompt requires.
    response_path = root / "agent-response.json"
    response_path.write_text('{"not_the_schema": true, "secret": "sk-testAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["ai", "task", "apply", "--task", str(task_path), "--from", str(response_path)],
    )
    assert result.exit_code == 1, result.output
    assert "AI call failed" in result.output

    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    rec = records[0]
    assert rec.adoption == "failed"
    assert rec.error_class == "LLMCallError"
    assert rec.error_message
    # The raw excerpt was persisted for diagnosis, scrubbed of key-shaped text.
    assert rec.raw_response_excerpt
    assert "sk-test" not in rec.raw_response_excerpt
    assert "<REDACTED>" in rec.raw_response_excerpt


def test_apply_broken_json_file_logged_as_failed(project) -> None:
    root, a, _, _ = project
    task_path = root / "task.json"
    result = CliRunner().invoke(
        app,
        ["ai", "task", "emit", "ExplainThisElement",
         "--inputs", json.dumps({"target_id": a.id}),
         "--output", str(task_path)],
    )
    assert result.exit_code == 0, result.output
    response_path = root / "agent-response.json"
    response_path.write_text("this is not json at all", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["ai", "task", "apply", "--task", str(task_path), "--from", str(response_path)],
    )
    assert result.exit_code == 1, result.output

    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    assert records[0].adoption == "failed"
    assert records[0].error_class == "LLMCallError"


def test_apply_missing_task_file_errors_cleanly(project) -> None:
    root, *_ = project
    response_path = _write_agent_response(root, {"explanation": "x", "referenced_ids": []})
    result = CliRunner().invoke(
        app,
        ["ai", "task", "apply", "--task", str(root / "nope.json"), "--from", str(response_path)],
    )
    assert result.exit_code != 0
    assert inter_ops.list_interactions(root=root) == []


# ---------- attribution ----------


def test_apply_actor_flag_reflected_in_model_id(project) -> None:
    root, a, _, _ = project
    task_path = root / "task.json"
    result = CliRunner().invoke(
        app,
        ["ai", "task", "emit", "ExplainThisElement",
         "--inputs", json.dumps({"target_id": a.id}),
         "--output", str(task_path)],
    )
    assert result.exit_code == 0, result.output
    response_path = _write_agent_response(root, {
        "explanation": "Price is a driver node.",
        "referenced_ids": [a.id],
    })

    result = CliRunner().invoke(
        app,
        ["ai", "task", "apply", "--task", str(task_path), "--from", str(response_path),
         "--actor", "claude-code"],
    )
    assert result.exit_code == 0, result.output

    records = inter_ops.list_interactions(root=root)
    assert records[0].model_id == "external-agent:claude-code"
    assert records[0].approved_by and records[0].approved_by.name == "Test Runner"
