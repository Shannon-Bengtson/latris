"""Shared formatting helpers for the report exporters."""

from __future__ import annotations

from typing import Any


def actor_name(actor: Any) -> str:
    """Display name for a Human/AI actor — name, else model id, else '?'."""
    return getattr(actor, "name", None) or getattr(actor, "model_id", "?")
