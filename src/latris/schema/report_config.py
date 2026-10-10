"""Report configuration — persisted, versioned Communicate-phase curation.

Promotes the GUI's report-builder state (selected sections, order, voice,
depth, saved presets) from browser localStorage to a git-versioned project
artifact. A Report is a real decision artifact and should be versioned like
everything else; persisting it also makes the formal report reproducible and
gives the Story feature a durable source for its "downstream of Report"
content selection (see docs/design/STORY.md → Companion change).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ReportPreset(_Base):
    """A saved, named report configuration."""

    name: str
    sections: list[str] = Field(default_factory=list)
    voice: str = "formal"
    depth: str = "standard"


class ReportConfig(_Base):
    """Persisted report-builder curation for the Communicate phase, scoped to a
    single model type (formalism).

    Section keys mirror the GUI's ``SECTION_META`` keys (e.g. ``"foundation"``,
    ``"nodes"``, ``"interp_answer"``). ``voice`` is one of
    formal|technical|executive|conversational; ``depth`` is one of
    summary|standard|detailed. An empty ``selected_sections`` means "not yet
    configured" — consumers fall back to their own defaults.
    """

    model_type: str = ""
    selected_sections: list[str] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)
    voice: str = "formal"
    depth: str = "standard"
    saved_presets: list[ReportPreset] = Field(default_factory=list)


class ReportConfigStore(_Base):
    """Top-level container persisted to ``communicate/report_config.yaml``.

    One ``ReportConfig`` per model type (mirrors ``StoryStore``); a
    multi-formalism project curates each formalism's report independently.
    """

    configs: list[ReportConfig] = Field(default_factory=list)
