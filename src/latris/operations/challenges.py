"""Challenge workflow — attack a model element, resolve to a terminal state.

Challenges are stored in ``ai/challenges.yaml`` and evolve through two states:
``open`` (default on creation) and one of six terminal states on resolution.
The presence of an open ``Challenge`` for a target surfaces in the GUI as a
``has_challenges`` derived badge — see ``operations/maturity.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

from latris.operations._actor import author as _author
from latris.operations._resolve import resolve_target as _resolve_target_id
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    Challenge,
    ChallengeLog,
    ChallengeState,
    ConversationTurn,
    Substrate,
    new_id,
)
from latris.schema.common import now_utc

TERMINAL_STATES: tuple[ChallengeState, ...] = tuple(s for s in get_args(ChallengeState) if s != "open")

_MIN_PREFIX = 4


def _resolve_challenge(query: str, entries: list[Challenge]) -> Challenge:
    exact = [c for c in entries if c.id == query]
    if len(exact) == 1:
        return exact[0]
    if "_" in query or len(query) >= _MIN_PREFIX:
        prefix = [c for c in entries if c.id.startswith(query)]
        if len(prefix) == 1:
            return prefix[0]
        if len(prefix) > 1:
            raise ValueError(f"challenge prefix {query!r} is ambiguous (matches: {', '.join(c.id for c in prefix)})")
    raise ValueError(f"no challenge matches {query!r}")


def list_challenges(root: Path | None = None) -> list[Challenge]:
    paths = require_project(root)
    return list(load_model(ChallengeLog, paths.challenges_yaml).entries)


def get_challenge(query: str, root: Path | None = None) -> Challenge:
    paths = require_project(root)
    log = load_model(ChallengeLog, paths.challenges_yaml)
    return _resolve_challenge(query, log.entries)


def open_challenge(
    target: str | None,
    argument: str,
    *,
    attribute: str | None = None,
    root: Path | None = None,
) -> tuple[Challenge, str]:
    paths = require_project(root)

    if target:
        substrate = load_model(Substrate, paths.conceptual_yaml)
        target_id: str | None = _resolve_target_id(target, substrate)
    else:
        target_id = None

    challenge = Challenge(
        id=new_id("challenge"),
        target_id=target_id,
        target_attribute=attribute,
        argument=argument,
        state="open",
        opened_by=_author(paths.root),
    )

    log = load_model(ChallengeLog, paths.challenges_yaml)
    log.entries.append(challenge)
    dump_model(log, paths.challenges_yaml)

    label = f"{target_id[:15]}…" if target_id else "model"
    suffix = f"/{attribute}" if attribute else ""
    sha = auto_commit(
        paths.root,
        subject=f"Opened challenge on {label}{suffix}",
        body=f"id: {challenge.id}\nargument: {argument}",
        paths=[paths.challenges_yaml],
    )
    return challenge, sha


def resolve_challenge(
    query: str,
    state: ChallengeState,
    *,
    rationale: str | None = None,
    root: Path | None = None,
) -> tuple[Challenge, str]:
    if state == "open":
        raise ValueError(f"cannot resolve to 'open' — pass one of: {', '.join(TERMINAL_STATES)}")
    if state not in get_args(ChallengeState):
        raise ValueError(f"unknown state {state!r}. Valid terminal states: {', '.join(TERMINAL_STATES)}")

    paths = require_project(root)
    log = load_model(ChallengeLog, paths.challenges_yaml)
    challenge = _resolve_challenge(query, log.entries)
    if challenge.state != "open":
        raise ValueError(f"challenge {challenge.id} is already resolved (state: {challenge.state!r})")

    challenge.state = state
    challenge.resolved_at = now_utc()
    challenge.resolution_rationale = rationale
    dump_model(log, paths.challenges_yaml)

    body_lines = [f"id: {challenge.id}", f"state: {state}"]
    if rationale:
        body_lines.append(f"rationale: {rationale}")
    sha = auto_commit(
        paths.root,
        subject=f"Resolved challenge {challenge.id[:20]}…: {state}",
        body="\n".join(body_lines),
        paths=[paths.challenges_yaml],
    )
    return challenge, sha


def add_turn(
    query: str,
    message: str,
    *,
    root: Path | None = None,
) -> tuple[Challenge, str]:
    paths = require_project(root)
    log = load_model(ChallengeLog, paths.challenges_yaml)
    challenge = _resolve_challenge(query, log.entries)
    if challenge.state != "open":
        raise ValueError(
            f"challenge {challenge.id} is closed ({challenge.state!r}) — "
            "cannot add conversation turns to a resolved challenge"
        )

    turn = ConversationTurn(speaker=_author(paths.root), message=message)
    challenge.conversation.append(turn)
    dump_model(log, paths.challenges_yaml)

    sha = auto_commit(
        paths.root,
        subject=f"Added turn to challenge {challenge.id[:20]}…",
        body=f"turn #{len(challenge.conversation)}",
        paths=[paths.challenges_yaml],
    )
    return challenge, sha
