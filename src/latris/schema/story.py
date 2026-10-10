"""Story schemas — the Communicate-phase scrollytelling artifact.

A Story is a self-contained, public-facing narrative generated downstream of
the Report and rendered to self-contained HTML. The ``StoryDoc`` is the source
of truth (persisted to ``communicate/story.yaml``, one doc per model type); the
HTML is a deterministic render. See ``docs/design/STORY.md``.

Beat prose reuses ``InterpretTextVersion`` so the AI-draft → human-edit →
version contract is identical to the Interpret phase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import now_utc
from latris.schema.interpretation import (
    InterpretSectionId,
    InterpretTextVersion,
)

StoryBeatKind = Literal[
    "hook",  # why we looked at this
    "system_tour",  # guided walk through key structure (one or more)
    "answer",  # what the model answered
    "uncertainty",  # what it can't answer / what's uncertain
    "implication",  # what this means for you
    "closing",  # provenance, next steps
    "freeform",  # author-authored, no canned source
]

StoryGenerationState = Literal["empty", "drafted", "edited"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())


class StoryEmphasis(_Base):
    """What the shared model graphic highlights for a beat.

    Loop selection is sugar: at authoring time it expands into the loop's
    member node/edge IDs (stored concretely so the binding survives findings
    regeneration); ``loop_ids`` is retained for re-sync. The renderer only ever
    needs ``node_ids`` + ``edge_ids``.
    """

    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    loop_ids: list[str] = Field(default_factory=list)
    mode: Literal["highlight"] = "highlight"


class StoryImage(_Base):
    """An uploaded graphic (framing/context, never model content).

    Stored versioned at ``communicate/assets/<asset_id>.<ext>`` and
    base64-inlined into the exported HTML so the artifact stays self-contained.
    """

    asset_id: str
    alt: str = ""
    caption: str = ""


class StoryBrand(_Base):
    """Optional brand overrides injected into the theme at export."""

    logo_asset_id: str | None = None
    accent: str | None = None  # hex colour
    font: str | None = None  # must be a bundled font


class StoryBeat(_Base):
    """A single narrative beat: lay-register prose + a graphic emphasis."""

    id: str
    kind: StoryBeatKind
    title: str = ""
    prose: str = ""
    prose_versions: list[InterpretTextVersion] = Field(default_factory=list)
    emphasis: StoryEmphasis = Field(default_factory=StoryEmphasis)
    show_confidence: bool = False
    # Provenance: which Interpret section this beat was drafted from.
    source_section: InterpretSectionId | None = None


class StoryGenerationRequest(_Base):
    """Saved generation request — captures the inherited Report selection and
    optional framing prompt so the draft is reproducible.
    """

    # Framing lens only — steers selection/emphasis/register, never new substance.
    prompt: str = ""
    include_sections: list[InterpretSectionId] = Field(default_factory=list)
    include_finding_ids: list[str] = Field(default_factory=list)
    source_report_selection: list[str] = Field(default_factory=list)
    drafted_at_commit: str = ""


class StoryDoc(_Base):
    """One Story, scoped to a single model type."""

    id: str
    model_type: str
    title: str = ""
    standfirst: str = ""  # one-line subtitle / hook
    title_image: StoryImage | None = None
    tone: Literal["public"] = "public"  # single register for v1; reserved for future audiences
    theme: str = "default"
    brand: StoryBrand | None = None
    request: StoryGenerationRequest | None = None
    beats: list[StoryBeat] = Field(default_factory=list)
    source_commit: str = ""  # HEAD when last drafted/anchored — staleness anchor
    generation_state: StoryGenerationState = "empty"
    updated_at: datetime = Field(default_factory=now_utc)


class StoryStore(_Base):
    """Top-level container persisted to ``communicate/story.yaml``.

    One ``StoryDoc`` per model type (a multi-formalism project can have several
    stories); multi-model synthesis is deferred.
    """

    docs: list[StoryDoc] = Field(default_factory=list)
