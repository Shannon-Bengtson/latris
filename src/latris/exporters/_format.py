"""Shared formatting helpers for the report exporters."""

from __future__ import annotations

from typing import Any

# "Made with Latris" badge — document-format exports (HTML, Markdown, Word)
# carry this footer link back to the product site; machine/diagram formats
# (DOT, SVG) deliberately do not. UTM params attribute site traffic to exports.
BADGE_TEXT = "Made with Latris"
BADGE_URL = "https://latris.app/?utm_source=latris-export&utm_medium=badge"


def actor_name(actor: Any) -> str:
    """Display name for a Human/AI actor — name, else model id, else '?'."""
    return getattr(actor, "name", None) or getattr(actor, "model_id", "?")
