"""End-to-end AI call orchestrator.

Flow:
1. Resolve project, config, model.
2. Build context via ``context.build_context``.
3. Stage API keys from keyring into env for the duration of the call.
4. Call the adapter (mock or litellm).
5. Render the proposal for the human (for read-only results, show + log, done).
6. Prompt ``[y/N]``.
7. Yes → ``proposal.apply(paths)`` + record_interaction(adoption=approved).
   No → record_interaction(adoption=rejected). No substrate mutation.

The orchestrator never commits directly — it always delegates to
``proposals.*.apply()`` which goes through ``operations/*`` which goes
through ``auto_commit``. One code path for mutation, many callers.

The interaction's adoption state is named ``adoption`` (not ``approval``)
so the word "approved" stays reserved for the unified Maturity ladder
on modelling artifacts; see docs/design/MATURITY_LADDER.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from latris.ai import config as ai_config
from latris.ai import credentials as creds
from latris.ai import interactions as inter_ops
from latris.ai import prompts as prompt_lib
from latris.ai.adapters import get_adapter
from latris.ai.adapters.base import ChatResult, LLMCallError
from latris.ai.context import ContextPack, build_context
from latris.repo.project import require_project


@dataclass
class CallOutcome:
    """What the orchestrator returns so the CLI can print a clean summary."""

    prompt_name: str
    model: str
    interaction_id: str
    # Whether the human adopted the AI proposal: "approved" | "rejected"
    # | "pending". Distinct from artifact maturity (see
    # docs/design/MATURITY_LADDER.md).
    adoption: str
    applied_ids: list[str]  # empty for rejected, read-only, or pending results
    cost_usd: float | None
    token_usage: dict[str, Any]
    rendered: str = ""  # human-readable rendering of the response (prose for
    # read-only prompts; proposal preview otherwise)
    proposal_json: dict[str, Any] | None = None  # serialised proposal for preview mode


# Map prompt_name → expected response pydantic class. The source of truth is
# now ``PromptSpec.response_model`` (see prompts.py); this is a derived alias
# kept for backwards compatibility with importers (server/routes/ai.py,
# cli/ai_cmd.py). Do not hand-edit — add the response model on the spec.
RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    name: spec.response_model
    for name, spec in prompt_lib.PROMPT_LIBRARY.items()
    if spec.response_model is not None
}


# Prompts where the LLM returns an intermediate result (e.g. search queries)
# that the server transforms into the real proposal. These have no apply() on
# their response model but must stay pending in preview mode so the user can
# approve/reject the final result.
_SERVER_TRANSFORMED_PROMPTS = {"ExpandBibliography", "FindFoundationalReferences"}

# Hybrid prompts produce critique prose AND a bounded structured proposal.
# The CLI prints the prose alongside the apply summary, so reviewers see
# both the critique and the audit-trail records that were created.
HYBRID_PROMPTS = {
    "AttackThisModel",
    "FindCounterPathway",
    "ScopeCheck",
    "IdentifyResearchGaps",
    "ScanEvidenceGaps",
    "CrossReferenceCheck",
    "EdgeReclassify",
    "ChallengeEdge",
    "EvidenceDemote",
    "VerifyClaimAgainstSource",
}


READ_ONLY_PROMPTS = {
    "ExplainThisElement",
    # RecommendApproach is read-only: the user accepts a recommendation, which
    # records a ModelChoice via its own route — the call never mutates.
    "RecommendApproach",
    # AttackThisModel, ScopeCheck, IdentifyResearchGaps, ScanEvidenceGaps,
    # and CrossReferenceCheck are now hybrid: their Result classes have
    # apply() methods that produce bounded provenance mutations
    # (assumptions, exclusions, questions, evidence-link suggestions)
    # alongside the critique prose that always renders into the report.
    # SyntheticPeerReview stays read-only — its value is the synthetic
    # external voice itself, and silent mutation from a synthetic
    # reviewer would erode the provenance distinction between
    # "AI surfaced a critique" and "the project formally accepted it".
    "RunElicitationInterview",
    "GeneratePack",
    "SyntheticPeerReview",
    "ProjectToFormalView",
    "SummarizeReference",
    # Compose extraction + synthesis (read-only)
    "ExtractVariablesFromEvidence",
    "ExtractCausalClaims",
    "SuggestVariables",
    "SuggestConnections",
    # SuggestEdgePolarities is *mutating* — its apply() commits all
    # suggestions via the Configure batch path. (Was previously read-only
    # because the GUI staged suggestions and applied them via a separate
    # /configure/apply-attributes call. The CLI dispatches apply directly.)
    # Inline per-field AI — GUI inserts value into editable field, user saves via normal mutation
    "FillProvenanceField",
    # Interpretation prompts (all read-only)
    "InterpretStructuralSummary",
    "InterpretKeyFindings",
    "InterpretSensitivity",
    "InterpretAssumptions",
    "InterpretEvidenceGaps",
    "InterpretEvidenceCoverage",
    "InterpretAnswer",
    "InterpretImplications",
    "InterpretConfidence",
    "InterpretOpenQuestions",
    # Story beat prose — register transform, no mutation
    "StoryBeatProse",
}


def _provider_for(model: str) -> str:
    """Guess the credential provider from a model name.

    litellm supports `provider/model` prefixes; if absent, infer from common
    substrings. Callers can override via ``LATRIS_AI_PROVIDER`` env.
    """
    import os

    override = os.environ.get("LATRIS_AI_PROVIDER")
    if override:
        return override.lower()
    if "/" in model:
        return model.split("/", 1)[0].lower()
    lowered = model.lower()
    if "claude" in lowered or "anthropic" in lowered:
        return "anthropic"
    if "gpt" in lowered or "o1" in lowered or "openai" in lowered:
        return "openai"
    if "gemini" in lowered:
        return "gemini"
    if "groq" in lowered or "llama" in lowered:
        return "groq"
    if "mistral" in lowered:
        return "mistral"
    if "deepseek" in lowered:
        return "deepseek"
    return "anthropic"  # last-resort default matches our default_model


def run_call(
    *,
    prompt_name: str,
    inputs: dict[str, Any],
    model_override: str | None = None,
    approver: Any,  # HumanActor — avoid schema import cycles
    confirm: callable,  # def confirm(proposal_rendered: str, parsed: BaseModel) -> bool
    render: callable,  # def render(parsed: BaseModel) -> str
    dry_run: bool = False,
    preview_only: bool = False,
    root: Path | None = None,
) -> CallOutcome:
    """Run a single AI call end-to-end.

    ``confirm`` is injected so the CLI can prompt interactively while tests
    pass a lambda that returns True/False directly.

    ``root`` pins the project directory explicitly. Pass it from any
    threaded context (the server) so the call does not depend on process
    cwd; CLI callers may omit it and rely on cwd discovery.
    """
    if prompt_name not in prompt_lib.PROMPT_LIBRARY:
        known = ", ".join(sorted(prompt_lib.PROMPT_LIBRARY.keys()))
        raise ValueError(f"unknown prompt {prompt_name!r}. Known: {known}")
    if prompt_name not in RESPONSE_MODELS:
        raise NotImplementedError(
            f"prompt {prompt_name!r} has a spec but no response model wired; "
            "only the M10 initial-cut prompts are runnable so far."
        )

    spec = prompt_lib.PROMPT_LIBRARY[prompt_name]
    paths = require_project(root)
    cfg = ai_config.load(paths)
    model = ai_config.resolve_model(paths, override=model_override)
    provider = _provider_for(model)
    response_cls = spec.response_model
    # Per-operation temperature beats the project/config default (extraction ops
    # run cool for consistent granularity); falls back to the config default.
    # Provider-mandated params (e.g. Moonshot temperature=1) override both
    # so those models never 400 at call time.
    temperature = spec.temperature if spec.temperature is not None else cfg.temperature
    temperature = ai_config.resolve_temperature(model, temperature)
    context: ContextPack = build_context(prompt_name, inputs, paths)

    if dry_run:
        # Assemble + return without calling the adapter or writing anything.
        import json

        # Stuff the assembled prompt into a fake CallOutcome so callers can
        # print it for inspection.
        payload = json.dumps(
            {
                "system": context.system,
                "user": context.user,
                "response_model": response_cls.__name__,
                "model": model,
                "provider": provider,
            },
            indent=2,
        )
        return CallOutcome(
            prompt_name=prompt_name,
            model=model,
            interaction_id="(dry-run)",
            adoption="dry-run",
            applied_ids=[payload],
            cost_usd=None,
            token_usage={},
        )

    adapter = get_adapter()
    try:
        with creds.key_in_env([provider]):
            # Real adapter will actually need the key; mock ignores.
            result: ChatResult = adapter.chat(
                model=model,
                system=context.system,
                user=context.user,
                response_model=response_cls,
                temperature=temperature,
                max_tokens=cfg.max_tokens,
            )
    except LLMCallError as exc:
        # Record the failure so it survives in the audit trail rather than
        # vanishing with the exception. Re-raise so CLI error handling
        # surfaces the message exactly as before.
        raw_response = getattr(exc, "raw_response", None)
        try:  # noqa: SIM105
            inter_ops.record_interaction(
                prompt_name=prompt_name,
                prompt_inputs=inputs,
                model_id=model,
                response_summary=f"FAILED: {type(exc).__name__}",
                response_full=None,
                target_ids=context.target_ids,
                related_attributes=context.related_attributes,
                adoption="failed",
                error_class=type(exc).__name__,
                error_message=str(exc),
                raw_response_excerpt=raw_response,
                root=paths.root,
            )
        except Exception:
            # If recording the failure itself fails we still want the
            # original error to surface — don't mask the real problem
            # with a logging hiccup.
            pass
        raise

    parsed = result.parsed
    rendered = render(parsed)

    # Preview mode: for mutation prompts, log as pending and return proposal
    # without applying. Read-only prompts are unaffected (nothing to approve).
    if (
        preview_only
        and prompt_name not in READ_ONLY_PROMPTS
        and (hasattr(parsed, "apply") or prompt_name in _SERVER_TRANSFORMED_PROMPTS)
    ):
        proposal_json = parsed.model_dump(mode="json")
        record, _ = inter_ops.record_interaction(
            prompt_name=prompt_name,
            prompt_inputs=inputs,
            model_id=result.model_id,
            response_summary=_summarise(parsed, rendered),
            response_full=parsed.model_dump_json(),
            target_ids=context.target_ids,
            related_attributes=context.related_attributes,
            token_usage=result.token_usage,
            cost_usd=result.cost_usd,
            root=paths.root,
        )
        # Leave adoption as "pending" — no set_adoption call.
        return CallOutcome(
            prompt_name=prompt_name,
            model=result.model_id,
            interaction_id=record.id,
            adoption="pending",
            applied_ids=[],
            cost_usd=result.cost_usd,
            token_usage=result.token_usage,
            rendered=rendered,
            proposal_json=proposal_json,
        )

    # Branch: read-only prompt or mutating proposal
    if prompt_name in READ_ONLY_PROMPTS or not hasattr(parsed, "apply"):
        # Just log and return — no approval gate because there's nothing to approve.
        record, _ = inter_ops.record_interaction(
            prompt_name=prompt_name,
            prompt_inputs=inputs,
            model_id=result.model_id,
            response_summary=_summarise(parsed, rendered),
            response_full=result.raw or rendered,
            target_ids=context.target_ids,
            related_attributes=context.related_attributes,
            token_usage=result.token_usage,
            cost_usd=result.cost_usd,
            root=paths.root,
        )
        # Read-only results land as "approved" (the content of the log entry
        # IS the deliverable — no proposal was pending).
        inter_ops.set_adoption(
            record.id,
            adoption="approved",
            approved_by=approver,
            root=paths.root,
        )
        return CallOutcome(
            prompt_name=prompt_name,
            model=result.model_id,
            interaction_id=record.id,
            adoption="approved",
            applied_ids=[],
            cost_usd=result.cost_usd,
            token_usage=result.token_usage,
            rendered=rendered,
            proposal_json=parsed.model_dump(mode="json"),
        )

    # Mutating proposal — confirm, then apply or reject.
    ok = confirm(rendered, parsed)
    if ok:
        try:
            applied_ids = parsed.apply(paths)
        except ValueError as exc:
            # Safety rail fired (e.g. citation fabrication). Log as rejected
            # and surface the error upward.
            record, _ = inter_ops.record_interaction(
                prompt_name=prompt_name,
                prompt_inputs=inputs,
                model_id=result.model_id,
                response_summary=f"refused by safety rail: {exc}",
                response_full=result.raw or rendered,
                target_ids=context.target_ids,
                related_attributes=context.related_attributes,
                root=paths.root,
            )
            inter_ops.set_adoption(
                record.id,
                adoption="rejected",
                approved_by=approver,
                root=paths.root,
            )
            raise
        record, _ = inter_ops.record_interaction(
            prompt_name=prompt_name,
            prompt_inputs=inputs,
            model_id=result.model_id,
            response_summary=_summarise(parsed, rendered),
            response_full=result.raw or rendered,
            target_ids=context.target_ids,
            related_attributes=context.related_attributes,
            proposal_ids=applied_ids,
            token_usage=result.token_usage,
            cost_usd=result.cost_usd,
            root=paths.root,
        )
        inter_ops.set_adoption(
            record.id,
            adoption="approved",
            approved_by=approver,
            root=paths.root,
        )
        return CallOutcome(
            prompt_name=prompt_name,
            model=result.model_id,
            interaction_id=record.id,
            adoption="approved",
            applied_ids=applied_ids,
            cost_usd=result.cost_usd,
            token_usage=result.token_usage,
            rendered=rendered,
        )

    # Rejected by user — log only, no mutation.
    record, _ = inter_ops.record_interaction(
        prompt_name=prompt_name,
        prompt_inputs=inputs,
        model_id=result.model_id,
        response_summary=_summarise(parsed, rendered),
        response_full=result.raw or rendered,
        target_ids=context.target_ids,
        related_attributes=context.related_attributes,
        root=paths.root,
    )
    inter_ops.set_adoption(
        record.id,
        adoption="rejected",
        approved_by=approver,
        root=paths.root,
    )
    return CallOutcome(
        prompt_name=prompt_name,
        model=result.model_id,
        interaction_id=record.id,
        adoption="rejected",
        applied_ids=[],
        cost_usd=result.cost_usd,
        token_usage=result.token_usage,
        rendered=rendered,
    )


def _summarise(parsed: BaseModel, rendered: str) -> str:
    """One-line summary for the interaction log."""
    if hasattr(parsed, "explanation"):
        text = getattr(parsed, "explanation", "")
        return (text[:117] + "…") if len(text) > 120 else text
    if hasattr(parsed, "argument"):
        text = getattr(parsed, "argument", "")
        return (text[:117] + "…") if len(text) > 120 else text
    # For CitationsProposal and anything else, fall back to a rendered preview.
    first_line = rendered.splitlines()[0] if rendered else parsed.__class__.__name__
    return (first_line[:117] + "…") if len(first_line) > 120 else first_line
