"""AI call endpoints — wraps run_call for the GUI.

Supports two modes:
- auto_apply=True (default): mutations apply immediately (like CLI --yes).
- auto_apply=False: mutations return a preview with proposal_json; the client
  then calls /apply/{id} or /reject/{id} to finalise.

Read-only prompts always auto-approve regardless of auto_apply.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from latris.ai import prompts as prompt_lib
from latris.ai.call import READ_ONLY_PROMPTS, RESPONSE_MODELS, run_call
from latris.ai.interactions import get_interaction, list_interactions, set_adoption
from latris.operations import ai_bibliography
from latris.repo import git
from latris.repo.project import require_project
from latris.schema import HumanActor
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/ai", tags=["ai"])

# In-memory cache for ExpandBibliography proposals.  The LLM returns search
# queries (BibliographySearchPlan); the server transforms them into real
# references (ExpandBibliographyProposal) via OpenAlex.  We cache the
# transformed proposal keyed by interaction_id so the apply endpoint can
# retrieve it.  Cleared on approve/reject.
_expand_bib_cache: dict[str, dict[str, Any]] = {}
Root = Annotated[Path, Depends(get_project_root)]


class AICallRequest(BaseModel):
    prompt_name: str
    inputs: dict[str, Any] = {}
    auto_apply: bool = True


class AIApplyRequest(BaseModel):
    selected_index: int | None = None
    approved_indices: list[int] | None = None


def _render(parsed: BaseModel) -> str:
    """Human-readable rendering of any proposal/result."""
    from latris.ai.render import render as ai_render

    # Determine prompt name from the calling context — fall back to class dispatch
    cls_name = parsed.__class__.__name__
    # Map response class names to prompt names for the renderer
    _CLS_TO_PROMPT = {
        "ExplanationResult": "ExplainThisElement",
        "ChallengeProposal": "ChallengeThisConnection",
        "CitationsProposal": "SuggestCitations",
        "DraftModelProposal": "DraftConceptualModel",
        "AttackResult": "AttackThisModel",
        "ScopeCheckResult": "ScopeCheck",
        "NewConnectionsProposal": "FindNewConnections",
        "ElicitationTurnResult": "RunElicitationInterview",
        "ReportDraft": "GeneratePack",
        "PeerReviewResult": "SyntheticPeerReview",
        "ResearchGapsResult": "IdentifyResearchGaps",
        "SteelmanProposal": "SteelmanOpposingView",
        "FormalViewProjectionResult": "ProjectToFormalView",
        "ExpandBibliographyProposal": "ExpandBibliography",
        "CrossReferenceCheckResult": "CrossReferenceCheck",
        "ReferenceRelevanceResult": "SummarizeReference",
        "AssumptionsProposal": "GenerateAssumptions",
        "DecisionsProposal": "SuggestDecisions",
        "ExclusionsProposal": "SuggestExclusions",
        "QuestionsProposal": "RaiseQuestions",
        "AttributeSuggestionsResult": "SuggestEdgePolarities",
        "FillFieldProposal": "FillProvenanceField",
        "EvidenceGapsScanResult": "ScanEvidenceGaps",
    }
    prompt_name = _CLS_TO_PROMPT.get(cls_name, "")
    return ai_render(prompt_name, parsed)


def _get_approver(root: Path) -> HumanActor:
    name, email = git.ensure_identity(root)
    return HumanActor(name=name, email=email)


@router.get("/prompts")
def list_prompts() -> list[dict[str, str | bool]]:
    """Return all canonical prompts with scope/intent metadata."""
    return [
        {
            "name": p.name,
            "title": p.title,
            "description": p.description,
            "scope": p.scope.value,
            "intent": p.intent.value,
            "wired": p.name in RESPONSE_MODELS,
        }
        for p in prompt_lib.list_all()
    ]


@router.post("/call")
def ai_call(body: AICallRequest, root: Root) -> dict[str, Any]:
    import logging
    import traceback

    from latris.ai.credentials import CredentialError

    try:
        approver = _get_approver(root)

        # For mutation prompts, preview_only when auto_apply is off.
        preview = not body.auto_apply

        def _auto_confirm(_rendered: str, parsed: object) -> bool:
            """Auto-approve with sensible defaults for selection fields."""
            if hasattr(parsed, "selected_index") and hasattr(parsed, "framings"):
                parsed.selected_index = 0
            if hasattr(parsed, "approved_indices") and hasattr(parsed, "proposals"):
                parsed.approved_indices = list(range(len(parsed.proposals)))
            return True

        outcome = run_call(
            prompt_name=body.prompt_name,
            inputs=body.inputs,
            approver=approver,
            confirm=_auto_confirm,
            render=_render,
            preview_only=preview,
            root=root,
        )

        proposal_json = outcome.proposal_json

        # ExpandBibliography (network-aware) and FindFoundationalReferences
        # (foundational, model-context-free) both follow the same flow: LLM
        # returns a BibliographySearchPlan; server runs Semantic Scholar to
        # produce a real ExpandBibliographyProposal.
        if body.prompt_name in ("ExpandBibliography", "FindFoundationalReferences"):
            import json as _json

            # Parse queries from the rendered output (it's the search plan JSON)
            try:
                plan_data = _json.loads(outcome.rendered)
            except (ValueError, TypeError):
                plan_data = {"queries": []}
            scoring_terms = ai_bibliography.extract_scoring_terms(root)
            bib_proposal = ai_bibliography.search_bibliography(plan_data, scoring_terms)
            # Cache the real proposal for the apply endpoint
            _expand_bib_cache[outcome.interaction_id] = bib_proposal
            # Render a human-readable summary of the real results
            refs = bib_proposal.get("new_references", [])
            rendered_lines = [f"Found {len(refs)} papers from Semantic Scholar:"]
            for r in refs:
                rendered_lines.append(f"  [{r['bibkey']}] {r['title']}")
                if r.get("authors"):
                    rendered_lines.append(
                        f"    {', '.join(r['authors'][:3])}" + (" et al." if len(r.get("authors", [])) > 3 else "")
                    )
                if r.get("url"):
                    rendered_lines.append(f"    {r['url']}")
            rendered = "\n".join(rendered_lines)
            return {
                "prompt_name": outcome.prompt_name,
                "model": outcome.model,
                "interaction_id": outcome.interaction_id,
                "adoption": "pending",
                "applied_ids": [],
                "cost_usd": outcome.cost_usd,
                "token_usage": outcome.token_usage,
                "rendered": rendered,
                "proposal": bib_proposal,
            }

        # SuggestCitations: still LLM-generated, validate URLs
        if proposal_json and body.prompt_name == "SuggestCitations":
            proposal_json = ai_bibliography.validate_proposal_urls(proposal_json)

        return {
            "prompt_name": outcome.prompt_name,
            "model": outcome.model,
            "interaction_id": outcome.interaction_id,
            "adoption": outcome.adoption,
            "applied_ids": outcome.applied_ids,
            "cost_usd": outcome.cost_usd,
            "token_usage": outcome.token_usage,
            "rendered": outcome.rendered,
            "proposal": proposal_json,
        }
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ValueError, LookupError, NotImplementedError):
        # Let app-level handlers return proper 4xx status codes.
        raise
    except Exception as exc:
        # Log the full traceback so it appears in server logs / Electron console,
        # and return the message to the client so packaged-app users can diagnose.
        logger = logging.getLogger(__name__)
        logger.exception("AI call failed")
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        ) from exc


@router.post("/apply/{interaction_id}")
def ai_apply(interaction_id: str, body: AIApplyRequest, root: Root) -> dict[str, Any]:
    """Apply a pending AI proposal after user review."""
    paths = require_project(root)
    approver = _get_approver(root)

    record = get_interaction(interaction_id, root=root)
    if record.adoption != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Interaction already {record.adoption}; cannot apply.",
        )

    prompt_name = record.prompt_name
    if prompt_name not in RESPONSE_MODELS:
        raise HTTPException(status_code=422, detail=f"No response model for {prompt_name}")
    if prompt_name in READ_ONLY_PROMPTS:
        raise HTTPException(status_code=422, detail=f"{prompt_name} is read-only; nothing to apply")

    # ExpandBibliography / FindFoundationalReferences: the real proposal
    # was built server-side from OpenAlex results and cached — retrieve
    # it instead of re-parsing the LLM's BibliographySearchPlan.
    if prompt_name in ("ExpandBibliography", "FindFoundationalReferences"):
        from latris.ai.proposals import ExpandBibliographyProposal

        bib_data = _expand_bib_cache.pop(interaction_id, None)
        if bib_data is None:
            raise HTTPException(
                status_code=410,
                detail="Bibliography proposal expired; please re-run Expand bibliography.",
            )
        proposal = ExpandBibliographyProposal.model_validate(bib_data)
        # Filter to user-selected references if indices provided.
        if body.approved_indices is not None:
            indices_set = set(body.approved_indices)
            proposal.new_references = [r for i, r in enumerate(proposal.new_references) if i in indices_set]
        applied_ids = proposal.apply(paths)
        set_adoption(record.id, adoption="approved", approved_by=approver, root=root)
        return {"applied_ids": applied_ids, "interaction_id": record.id}

    # Re-parse the proposal from the stored JSON.
    response_cls = RESPONSE_MODELS[prompt_name]
    try:
        proposal = response_cls.model_validate_json(record.response_full)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to re-parse proposal: {exc}") from exc

    # Inject user selections.
    if body.selected_index is not None and hasattr(proposal, "selected_index"):
        proposal.selected_index = body.selected_index
    if body.approved_indices is not None and hasattr(proposal, "approved_indices"):
        proposal.approved_indices = body.approved_indices

    # For CitationsProposal, filter to approved items if indices provided.
    if (
        body.approved_indices is not None
        and hasattr(proposal, "new_references")
        and hasattr(proposal, "evidence_links")
    ):
        indices_set = set(body.approved_indices)
        proposal.new_references = [r for i, r in enumerate(proposal.new_references) if i in indices_set]
        proposal.evidence_links = [
            e
            for i, e in enumerate(proposal.evidence_links)
            if i + len(proposal.new_references) in indices_set or i in indices_set
        ]

    applied_ids = proposal.apply(paths)

    set_adoption(record.id, adoption="approved", approved_by=approver, root=root)

    return {"applied_ids": applied_ids, "interaction_id": record.id}


@router.post("/reject/{interaction_id}")
def ai_reject(interaction_id: str, root: Root) -> dict[str, Any]:
    """Reject a pending AI proposal."""
    _expand_bib_cache.pop(interaction_id, None)  # clean up if ExpandBibliography
    record = get_interaction(interaction_id, root=root)
    if record.adoption != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Interaction already {record.adoption}; cannot reject.",
        )

    name, email = git.ensure_identity(root)
    approver = HumanActor(name=name, email=email)
    set_adoption(record.id, adoption="rejected", approved_by=approver, root=root)

    return {"ok": True, "interaction_id": record.id}


@router.get("/interactions")
def get_interactions(root: Root, limit: int = 20) -> list[dict[str, Any]]:
    items = list_interactions(limit=limit, root=root)
    return [i.model_dump(mode="json") for i in items]


# ---------- Chain endpoints ----------


class ChainStartRequest(BaseModel):
    chain_name: str
    inputs: dict[str, Any] = {}


@router.get("/chains")
def list_chains_endpoint() -> list[dict[str, Any]]:
    """List available prompt chains."""
    from latris.ai.chains import list_chains

    return [
        {
            "name": c.name,
            "title": c.title,
            "description": c.description,
            "step_count": c.step_count,
            "steps": [s.prompt_name for s in c.steps],
        }
        for c in list_chains()
    ]


@router.post("/chain/start")
def chain_start(body: ChainStartRequest, root: Root) -> dict[str, Any]:
    """Start a new prompt chain, execute step 0, return session + first result."""
    from latris.ai import chain_runner
    from latris.ai.chains import CHAIN_LIBRARY

    if body.chain_name not in CHAIN_LIBRARY:
        raise HTTPException(status_code=404, detail=f"Unknown chain: {body.chain_name}")

    approver = _get_approver(root)

    session, outcome = chain_runner.start_chain(
        body.chain_name,
        body.inputs,
        approver=approver,
        render=_render,
        root=root,
    )

    return {
        "session_id": session.id,
        "chain_name": session.chain_name,
        "step_index": session.current_step,
        "total_steps": session.total_steps,
        "step_prompt_name": outcome.prompt_name,
        "chain_status": session.status,
        "result": {
            "prompt_name": outcome.prompt_name,
            "model": outcome.model,
            "interaction_id": outcome.interaction_id,
            "adoption": outcome.adoption,
            "applied_ids": outcome.applied_ids,
            "cost_usd": outcome.cost_usd,
            "token_usage": outcome.token_usage,
            "rendered": outcome.rendered,
            "proposal": outcome.proposal_json,
        },
    }


@router.post("/chain/advance/{session_id}")
def chain_advance(session_id: str, body: AIApplyRequest, root: Root) -> dict[str, Any]:
    """Approve current step and advance to next. Apply the pending proposal first."""
    from latris.ai import chain_runner

    try:
        session = chain_runner.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No active chain session: {session_id}") from exc

    approver = _get_approver(root)

    # Apply the pending proposal from the current step
    if session.pending_interaction_id:
        with suppress(HTTPException):
            ai_apply(session.pending_interaction_id, body, root)

    session_out, outcome = chain_runner.advance_chain(
        session_id,
        approver=approver,
        render=_render,
        root=root,
    )

    result: dict[str, Any] = {
        "session_id": session_out.id,
        "chain_name": session_out.chain_name,
        "step_index": session_out.current_step,
        "total_steps": session_out.total_steps,
        "chain_status": session_out.status,
    }
    if outcome:
        result["step_prompt_name"] = outcome.prompt_name
        result["result"] = {
            "prompt_name": outcome.prompt_name,
            "model": outcome.model,
            "interaction_id": outcome.interaction_id,
            "adoption": outcome.adoption,
            "applied_ids": outcome.applied_ids,
            "cost_usd": outcome.cost_usd,
            "token_usage": outcome.token_usage,
            "rendered": outcome.rendered,
            "proposal": outcome.proposal_json,
        }
    return result


@router.post("/chain/reject-step/{session_id}")
def chain_reject_step(session_id: str, root: Root) -> dict[str, Any]:
    """Reject current step and advance to next."""
    from latris.ai import chain_runner

    try:
        session = chain_runner.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No active chain session: {session_id}") from exc

    approver = _get_approver(root)

    # Reject the pending interaction if it exists
    if session.pending_interaction_id:
        with suppress(HTTPException):
            ai_reject(session.pending_interaction_id, root)

    session_out, outcome = chain_runner.reject_step(
        session_id,
        approver=approver,
        render=_render,
        root=root,
    )

    result: dict[str, Any] = {
        "session_id": session_out.id,
        "chain_name": session_out.chain_name,
        "step_index": session_out.current_step,
        "total_steps": session_out.total_steps,
        "chain_status": session_out.status,
    }
    if outcome:
        result["step_prompt_name"] = outcome.prompt_name
        result["result"] = {
            "prompt_name": outcome.prompt_name,
            "model": outcome.model,
            "interaction_id": outcome.interaction_id,
            "adoption": outcome.adoption,
            "applied_ids": outcome.applied_ids,
            "cost_usd": outcome.cost_usd,
            "token_usage": outcome.token_usage,
            "rendered": outcome.rendered,
            "proposal": outcome.proposal_json,
        }
    return result


@router.post("/chain/abort/{session_id}")
def chain_abort(session_id: str) -> dict[str, Any]:
    """Abort chain entirely."""
    from latris.ai import chain_runner

    try:
        session = chain_runner.abort_chain(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No active chain session: {session_id}") from exc

    return {
        "session_id": session.id,
        "chain_name": session.chain_name,
        "chain_status": session.status,
        "completed_steps": session.current_step,
    }
