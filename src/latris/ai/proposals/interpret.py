"""The interpretation result: one report section's prose."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import _Base


class InterpretProseResult(_Base):
    """Interpret* prompt output. Read-only — AI-generated interpretation prose."""

    prose: str = Field(..., description="The generated interpretation text (Markdown).")
    key_references: list[str] = Field(
        default_factory=list,
        description="Finding or reference IDs cited in the interpretation.",
    )
