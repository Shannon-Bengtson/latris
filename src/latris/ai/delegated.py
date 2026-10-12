"""Delegated AI calls — bring your own agent.

An external terminal agent (Claude Code, Kimi, …) can answer any of the
closed prompt library's prompts **without an API key**:

1. ``build_task_package`` assembles a self-contained task package (prompt
   metadata, assembled context, output JSON schema, instructions). It reads
   the project but writes nothing — no adapter call, no interaction log.
2. The agent answers with a JSON document matching ``response_schema``.
3. ``finalize_delegated`` ingests that answer through the SAME
   validate → render → human-approve → apply → interaction-log pipeline
   that adapter responses use (``call._finalize_call``).

Attribution convention: the interaction's ``model_id`` is
``"external-agent"`` (or ``"external-agent:<actor>"`` when the caller
passes ``--actor``); ``approved_by`` remains the human who ran the apply —
the approval gate is unchanged. Read-only prompts keep their no-confirm
branch; mutating prompts keep the confirm gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from latris.ai import call as call_module
from latris.ai import interactions as inter_ops
from latris.ai import prompts as prompt_lib
from latris.ai.adapters.base import LLMCallError, redact_secrets
from latris.ai.context import build_context
from latris.repo.project import require_project

TASK_VERSION = 1


def build_task_package(
    prompt_name: str,
    inputs: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Assemble a self-contained task package an external agent can answer.

    Prompt validation, project resolution, and context assembly happen here;
    nothing is written to the project and no credentials are touched, so this
    works with no API key and regardless of ``LATRIS_AI_MOCK``.
    """
    if prompt_name not in prompt_lib.PROMPT_LIBRARY:
        known = ", ".join(sorted(prompt_lib.PROMPT_LIBRARY.keys()))
        raise ValueError(f"unknown prompt {prompt_name!r}. Known: {known}")
    spec = prompt_lib.PROMPT_LIBRARY[prompt_name]
    if spec.response_model is None:
        raise NotImplementedError(
            f"prompt {prompt_name!r} has a spec but no response model wired; "
            "only the M10 initial-cut prompts are runnable so far."
        )
    paths = require_project(root)
    context = build_context(prompt_name, inputs, paths)
    return {
        "task_version": TASK_VERSION,
        "prompt_name": prompt_name,
        "title": spec.title,
        "intent": spec.intent.value,
        "scope": spec.scope.value,
        "inputs": inputs,
        "system": context.system,
        "user": context.user,
        "response_schema": spec.response_model.model_json_schema(),
        "instructions": _instructions(),
    }


def _instructions() -> str:
    return (
        "You are answering a Latris AI task on behalf of a human modeller. "
        "Return ONLY a JSON object that matches `response_schema` exactly — "
        "no markdown fences, no commentary before or after the JSON. "
        "Never fabricate citations or invent node/edge IDs; when unsure, say "
        "so in a rationale/explanation field rather than guessing — "
        "fabricated citations are refused when the answer is applied. "
        "Write your JSON to a file, then hand it back with:\n"
        "    latris ai task apply --task <task-file> --from <response.json>"
    )


def load_task(
    path: str | Path,
    *,
    root: Path | None = None,
) -> tuple[prompt_lib.PromptSpec, dict[str, Any]]:
    """Read a task package back; return its spec and inputs.

    The task file is the single source of truth for the apply: ``prompt_name``
    and ``inputs`` are read from it, not from CLI flags.
    """
    task_path = Path(path)
    try:
        raw = task_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read task file {task_path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"task file {task_path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"task file {task_path} must contain a JSON object")
    if data.get("task_version") != TASK_VERSION:
        raise ValueError(
            f"task file {task_path} has unsupported task_version "
            f"{data.get('task_version')!r} (expected {TASK_VERSION})"
        )
    prompt_name = data.get("prompt_name")
    if not isinstance(prompt_name, str) or not prompt_name:
        raise ValueError(f"task file {task_path} is missing a 'prompt_name' string")
    if prompt_name not in prompt_lib.PROMPT_LIBRARY:
        known = ", ".join(sorted(prompt_lib.PROMPT_LIBRARY.keys()))
        raise ValueError(f"unknown prompt {prompt_name!r}. Known: {known}")
    spec = prompt_lib.PROMPT_LIBRARY[prompt_name]
    if spec.response_model is None:
        raise NotImplementedError(
            f"prompt {prompt_name!r} has a spec but no response model wired; "
            "only the M10 initial-cut prompts are runnable so far."
        )
    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise ValueError(f"task file {task_path}: 'inputs' must be a JSON object")
    return spec, inputs


def parse_response(spec: prompt_lib.PromptSpec, text: str) -> BaseModel:
    """Validate an external agent's answer against the prompt's response model.

    Raises ``LLMCallError`` carrying the raw text on validation failure so the
    caller can persist a redacted excerpt in the interaction log and the CLI
    surfaces a clean exit-1. No auto-repair: the agent fixes its answer and
    resubmits.
    """
    assert spec.response_model is not None
    try:
        return spec.response_model.model_validate_json(text)
    except ValidationError as exc:
        raise LLMCallError(
            f"agent response failed validation against {spec.response_model.__name__}: {exc}",
            raw_response=text,
        ) from exc


def finalize_delegated(
    *,
    task_path: str | Path,
    response_path: str | Path,
    actor: str | None,
    approver: Any,  # HumanActor — avoid schema import cycles
    confirm: callable,  # def confirm(proposal_rendered: str, parsed: BaseModel) -> bool
    render: callable,  # def render(parsed: BaseModel) -> str
    root: Path | None = None,
) -> call_module.CallOutcome:
    """Ingest an external agent's answer through the shared call pipeline.

    Task → spec/inputs → context → validate response → ``call._finalize_call``
    with ``model_id="external-agent[:actor]"``, ``token_usage={}``,
    ``cost_usd=None``. A validation failure is recorded as an
    ``adoption="failed"`` interaction (excerpt run through ``redact_secrets``)
    and re-raised as ``LLMCallError``.
    """
    spec, inputs = load_task(task_path, root=root)
    paths = require_project(root)
    context = build_context(spec.name, inputs, paths)
    model_id = f"external-agent:{actor}" if actor else "external-agent"
    response_file = Path(response_path)
    try:
        response_text = response_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read response file {response_file}: {exc}") from exc

    try:
        parsed = parse_response(spec, response_text)
    except LLMCallError as exc:
        # Same contract as run_call's adapter-failure branch: the failure is
        # recorded in the audit trail, then re-raised for the CLI to surface.
        raw_response = getattr(exc, "raw_response", None)
        try:  # noqa: SIM105
            inter_ops.record_interaction(
                prompt_name=spec.name,
                prompt_inputs=inputs,
                model_id=model_id,
                response_summary=f"FAILED: {type(exc).__name__}",
                response_full=None,
                target_ids=context.target_ids,
                related_attributes=context.related_attributes,
                adoption="failed",
                error_class=type(exc).__name__,
                error_message=str(exc),
                raw_response_excerpt=redact_secrets(raw_response) if raw_response else None,
                root=paths.root,
            )
        except Exception:
            # If recording the failure itself fails we still want the
            # original error to surface — don't mask the real problem
            # with a logging hiccup.
            pass
        raise

    return call_module._finalize_call(
        prompt_name=spec.name,
        inputs=inputs,
        context=context,
        parsed=parsed,
        raw=response_text,
        model_id=model_id,
        token_usage={},
        cost_usd=None,
        approver=approver,
        confirm=confirm,
        render=render,
        preview_only=False,
        paths=paths,
    )
