"""Recognise when an AI agent is driving the CLI, and record it honestly.

The CLI commits as the configured git identity — the responsible person —
whoever types the command. An AI agent (Claude Code, or any tool that
follows the ``AI_AGENT`` convention) runs commands in a shell that says so;
when it does, the CLI:

- records new work as ``ai-proposed`` (unless ``LATRIS_DEFAULT_ORIGIN`` says
  otherwise);
- defaults "who checked / wrote this" options (``--by``, ``--verified-by``)
  to ``ai``;
- asks for ``--confirmed-by-person`` before recording a person's judgement —
  an approval, review, sign-off, resolved challenge or a check ``--by human``.
  People who build in a chat review there and ask the agent to record it;
  the flag is the agent saying that's what happened;
- adds a ``Recorded-by-agent:`` trailer to every commit.

This catches the honest default, not a determined impersonation: anything
that can run a shell can unset these variables or edit the files. Proving a
person approved needs an identity check the agent can't complete (signing
in to the app; signed commits) — see docs/engineering/AI_LAYER.md.

``LATRIS_AGENT=<name>`` declares an agent explicitly; ``LATRIS_AGENT=none``
turns detection off (e.g. a person's own terminal that inherits the
variables).
"""

from __future__ import annotations

import os

import typer

from latris.operations.commit import FOR_PERSON_ENV, RECORDED_BY_AGENT_ENV
from latris.schema.common import DEFAULT_ORIGIN_ENV

AGENT_ENV = "LATRIS_AGENT"


def detected_agent() -> str | None:
    """The name of the AI agent running this process, or None for a person."""
    explicit = os.environ.get(AGENT_ENV, "").strip()
    if explicit:
        return None if explicit.lower() in {"none", "0", "false", "no"} else explicit
    named = os.environ.get("AI_AGENT", "").strip()
    if named:
        return named
    if os.environ.get("CLAUDECODE", "").strip() == "1":
        return "claude-code"
    return None


def apply_agent_defaults() -> None:
    """Called once per CLI invocation, before the command runs."""
    agent = detected_agent()
    if agent is None:
        return
    os.environ.setdefault(DEFAULT_ORIGIN_ENV, "ai-proposed")
    os.environ[RECORDED_BY_AGENT_ENV] = agent


def default_by(value: str | None) -> str:
    """Resolve a ``--by`` / ``--verified-by`` left unset: ``ai`` under an agent, else ``human``."""
    if value is not None:
        return value
    return "ai" if detected_agent() else "human"


CONFIRMED_BY_PERSON = typer.Option(
    False,
    "--confirmed-by-person",
    help="For AI agents: the person reviewed this themselves and asked you to record it. "
    "Not needed when a person runs the command.",
)


def require_person(confirmed: bool, action: str) -> None:
    """Gate an action that records a person's judgement when an agent runs it."""
    agent = detected_agent()
    if agent is None:
        return
    if not confirmed:
        raise ValueError(
            f"{action} records a person's judgement, and this command is being run by an AI agent ({agent}). "
            "If the person reviewed it themselves and asked you to record it, re-run with "
            "--confirmed-by-person (the commit notes that you recorded it for them). Otherwise leave it "
            "for them to do."
        )
    os.environ[FOR_PERSON_ENV] = "1"
