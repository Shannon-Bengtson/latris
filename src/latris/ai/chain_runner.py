"""Chain session management — step-at-a-time execution.

The frontend drives chain advancement by calling advance/reject/abort.
State is ephemeral (in-memory dict) — acceptable for a single-user
desktop app. If the server restarts, active chains are lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from latris.ai.call import CallOutcome, run_call
from latris.ai.chains import CHAIN_LIBRARY, ChainSpec
from latris.schema import new_id


@dataclass
class ChainSession:
    """Tracks the state of an in-progress chain."""

    id: str
    chain_name: str
    trigger_inputs: dict[str, Any]
    current_step: int
    total_steps: int
    outcomes: list[CallOutcome] = field(default_factory=list)
    status: Literal["active", "completed", "aborted"] = "active"
    pending_interaction_id: str | None = None


# Ephemeral session store — single-user desktop app, no persistence needed.
_sessions: dict[str, ChainSession] = {}


def start_chain(
    chain_name: str,
    inputs: dict[str, Any],
    *,
    approver: Any,
    render: callable,
    root: Path | None = None,
) -> tuple[ChainSession, CallOutcome]:
    """Start a new chain, execute step 0, return session + first result."""
    spec = CHAIN_LIBRARY[chain_name]
    session = ChainSession(
        id=new_id("chain"),
        chain_name=chain_name,
        trigger_inputs=inputs,
        current_step=0,
        total_steps=spec.step_count,
    )
    _sessions[session.id] = session

    outcome = _run_current_step(session, spec, approver=approver, render=render, root=root)
    return session, outcome


def advance_chain(
    session_id: str,
    *,
    approver: Any,
    render: callable,
    root: Path | None = None,
) -> tuple[ChainSession, CallOutcome | None]:
    """Advance to the next step after approval. Returns None if chain is complete."""
    session = _sessions[session_id]
    if session.status != "active":
        raise ValueError(f"Chain {session_id} is {session.status}, cannot advance.")

    session.current_step += 1
    if session.current_step >= session.total_steps:
        session.status = "completed"
        return session, None

    spec = CHAIN_LIBRARY[session.chain_name]
    outcome = _run_current_step(session, spec, approver=approver, render=render, root=root)
    return session, outcome


def reject_step(
    session_id: str,
    *,
    approver: Any,
    render: callable,
    root: Path | None = None,
) -> tuple[ChainSession, CallOutcome | None]:
    """Reject current step (logged as rejected), then advance to next step."""
    session = _sessions[session_id]
    if session.status != "active":
        raise ValueError(f"Chain {session_id} is {session.status}, cannot reject step.")

    # Record a "rejected" outcome for this step
    rejected_outcome = CallOutcome(
        prompt_name=CHAIN_LIBRARY[session.chain_name].steps[session.current_step].prompt_name,
        model="(rejected)",
        interaction_id=session.pending_interaction_id or "(skipped)",
        adoption="rejected",
        applied_ids=[],
        cost_usd=None,
        token_usage={},
    )
    session.outcomes.append(rejected_outcome)

    # Advance to next step
    session.current_step += 1
    if session.current_step >= session.total_steps:
        session.status = "completed"
        return session, None

    spec = CHAIN_LIBRARY[session.chain_name]
    outcome = _run_current_step(session, spec, approver=approver, render=render, root=root)
    return session, outcome


def abort_chain(session_id: str) -> ChainSession:
    """Abort the chain entirely."""
    session = _sessions[session_id]
    session.status = "aborted"
    return session


def get_session(session_id: str) -> ChainSession:
    """Get session state."""
    if session_id not in _sessions:
        raise KeyError(f"No active chain session: {session_id}")
    return _sessions[session_id]


def _run_current_step(
    session: ChainSession,
    spec: ChainSpec,
    *,
    approver: Any,
    render: callable,
    root: Path | None = None,
) -> CallOutcome:
    """Execute the current step and record the outcome."""
    step = spec.steps[session.current_step]
    step_inputs = step.input_builder(session.trigger_inputs, session.outcomes)

    outcome = run_call(
        prompt_name=step.prompt_name,
        inputs=step_inputs,
        approver=approver,
        confirm=lambda _r, _p: True,  # auto-confirm in chain mode (GUI handles approval)
        render=render,
        preview_only=True,  # always preview — GUI decides approval
        root=root,
    )

    session.pending_interaction_id = outcome.interaction_id
    session.outcomes.append(outcome)
    return outcome
