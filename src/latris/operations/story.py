"""Story operations — draft, prose, emphasis, persistence (Communicate phase).

The Story is generated *downstream of the Report*: a deterministic beat
skeleton (the hook → … → closing arc, mapped from the ticked Interpret
sources, emphasis seeded from detected loops) plus AI-generated public-register
prose per beat. Mirrors the Interpret contract — the structure is deterministic
and auditable; the AI only transforms register, never substance.

See docs/design/STORY.md.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations.commit import auto_commit
from latris.operations.findings import list_findings
from latris.operations.interpret import load_interpretation
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.common import HumanActor, now_utc
from latris.schema.ids import new_id
from latris.schema.interpretation import InterpretSectionId, InterpretTextVersion
from latris.schema.project import ProjectFoundation
from latris.schema.story import (
    StoryBeat,
    StoryBeatKind,
    StoryDoc,
    StoryEmphasis,
    StoryGenerationRequest,
    StoryStore,
)

# Default narrative arc: (kind, source Interpret section, default title, show_confidence).
# A beat is included when its source is None (always), its source is ticked,
# or it is the uncertainty beat (default-on — the credibility moat).
_ARC: list[tuple[StoryBeatKind, InterpretSectionId | None, str, bool]] = [
    ("hook", None, "Why this matters", False),
    ("system_tour", "key_findings", "How the system works", False),
    ("answer", "answer_to_question", "What we found", True),
    ("uncertainty", "open_questions", "What we're less sure about", True),
    ("implication", "implications", "What this means for you", False),
    ("closing", None, "Where to next", False),
]

_ALWAYS_ON: set[StoryBeatKind] = {"hook", "uncertainty", "closing"}


# ── Loading / saving ────────────────────────────────────────────────────


def load_story(*, root: Path | None = None) -> StoryStore:
    """Load the story store from YAML (empty if file absent)."""
    paths = require_project(root)
    if paths.story_yaml.exists():
        return load_model(StoryStore, paths.story_yaml)
    return StoryStore()


def _save(store: StoryStore, *, subject: str, root: Path | None = None) -> str:
    paths = require_project(root)
    dump_model(store, paths.story_yaml)
    return auto_commit(paths.root, subject=subject, paths=[paths.story_yaml])


def _find_doc(store: StoryStore, model_type: str, *, create: bool = False) -> StoryDoc:
    for doc in store.docs:
        if doc.model_type == model_type:
            return doc
    if not create:
        raise ValueError(f"no story for model type {model_type!r}")
    doc = StoryDoc(id=new_id("story"), model_type=model_type)
    store.docs.append(doc)
    return doc


def _find_beat(doc: StoryDoc, beat_id: str) -> StoryBeat:
    for beat in doc.beats:
        if beat.id == beat_id or beat.id.startswith(beat_id):
            return beat
    raise ValueError(f"no beat matches {beat_id!r}")


# ── Emphasis / loops ────────────────────────────────────────────────────


def _loop_findings(model_type: str, *, root: Path | None) -> list:
    """Structure findings that carry loop membership in their payload."""
    findings = list_findings(category="structure", model_type=model_type, root=root)
    return [f for f in findings if f.payload.get("node_ids")]


def _expand_loops(model_type: str, loop_ids: list[str], *, root: Path | None) -> tuple[list[str], list[str]]:
    """Resolve loop (structure-finding) IDs into member node/edge IDs."""
    by_id = {f.id: f for f in _loop_findings(model_type, root=root)}
    nodes: list[str] = []
    edges: list[str] = []
    for fid in loop_ids:
        f = by_id.get(fid)
        if f is None:
            continue
        nodes.extend(f.payload.get("node_ids", []))
        edges.extend(f.payload.get("edge_ids", []))
    return list(dict.fromkeys(nodes)), list(dict.fromkeys(edges))


# ── Draft ───────────────────────────────────────────────────────────────


def draft_story(
    model_type: str,
    request: StoryGenerationRequest,
    *,
    root: Path | None = None,
) -> tuple[StoryDoc, str]:
    """Build (or rebuild) the deterministic beat skeleton for a model type.

    Beats follow the canned arc, filtered to the request's ticked sources
    (the uncertainty/hook/closing beats are always-on). The system-tour beat's
    emphasis is seeded from the first detected loop. Prose is left empty
    (generation_state="drafted") for per-beat AI generation.
    """
    paths = require_project(root)
    store = load_story(root=root)
    doc = _find_doc(store, model_type, create=True)
    head = git.head_sha(paths.root)

    include = set(request.include_sections)
    loops = _loop_findings(model_type, root=root)
    tour_nodes, tour_edges, tour_loop_ids = ([], [], [])
    if loops:
        first = loops[0]
        tour_nodes = list(first.payload.get("node_ids", []))
        tour_edges = list(first.payload.get("edge_ids", []))
        tour_loop_ids = [first.id]

    beats: list[StoryBeat] = []
    for kind, source, title, show_conf in _ARC:
        if source is not None and source not in include and kind not in _ALWAYS_ON:
            continue
        emphasis = StoryEmphasis()
        if kind == "system_tour" and (tour_nodes or tour_edges):
            emphasis = StoryEmphasis(node_ids=tour_nodes, edge_ids=tour_edges, loop_ids=tour_loop_ids)
        beats.append(
            StoryBeat(
                id=new_id("story-beat"),
                kind=kind,
                title=title,
                emphasis=emphasis,
                show_confidence=show_conf,
                source_section=source,
            )
        )

    doc.beats = beats
    request.drafted_at_commit = head
    doc.request = request
    doc.source_commit = head
    doc.generation_state = "drafted"
    doc.updated_at = now_utc()
    if not doc.title:
        foundation = load_model(ProjectFoundation, paths.project_yaml)
        doc.title = foundation.name or "Model story"
        doc.standfirst = foundation.statement

    sha = _save(store, subject=f"Story: draft skeleton ({model_type})", root=root)
    return doc, sha


# ── Prose ───────────────────────────────────────────────────────────────


def _source_text_for_beat(paths, doc: StoryDoc, beat: StoryBeat) -> str:
    """The grounded content a beat's prose is rewritten from."""
    if beat.source_section is not None:
        interp = load_interpretation(root=paths.root)
        for s in interp.sections:
            if s.section_type == beat.source_section and s.model_type == doc.model_type:
                return s.prose or "\n".join(s.claims)
        return ""
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    if beat.kind == "hook":
        return f"{foundation.statement}\n\n{foundation.background}".strip()
    return "This story was produced from an evidence-grounded model. Findings trace to their sources."


def set_beat_prose(
    model_type: str,
    beat_id: str,
    prose: str,
    *,
    source: str = "human-edit",
    root: Path | None = None,
) -> tuple[StoryBeat, str]:
    """Persist beat prose with a version record (mirrors Interpret)."""
    paths = require_project(root)
    store = load_story(root=root)
    doc = _find_doc(store, model_type)
    beat = _find_beat(doc, beat_id)

    beat.prose = prose
    beat.prose_versions.append(
        InterpretTextVersion(
            version_id=new_id("version"),
            text=prose,
            source="ai" if source == "ai" else "human-edit",
            model_commit=git.head_sha(paths.root),
        )
    )
    if source == "human-edit":
        doc.generation_state = "edited"
    doc.updated_at = now_utc()
    sha = _save(store, subject=f"Story: update beat prose ({beat.kind})", root=root)
    return beat, sha


def generate_beat_prose(
    model_type: str,
    beat_id: str,
    *,
    approver: HumanActor | None = None,
    root: Path | None = None,
) -> tuple[StoryBeat, str]:
    """Generate public-register prose for a beat via the StoryBeatProse prompt.

    The AI transforms the beat's grounded source content into plain language;
    it must not introduce new substance. The result is persisted as an
    AI-sourced prose version.
    """
    from latris.ai.call import run_call
    from latris.ai.render import render as ai_render

    paths = require_project(root)
    store = load_story(root=root)
    doc = _find_doc(store, model_type)
    beat = _find_beat(doc, beat_id)
    source_text = _source_text_for_beat(paths, doc, beat)

    if approver is None:
        name, email = git.ensure_identity(paths.root)
        approver = HumanActor(name=name, email=email)

    outcome = run_call(
        prompt_name="StoryBeatProse",
        inputs={
            "beat_kind": beat.kind,
            "source_text": source_text,
            "model_type": model_type,
            "_prompt_name": "StoryBeatProse",
        },
        approver=approver,
        confirm=lambda _r, _p: True,
        render=lambda parsed: ai_render("StoryBeatProse", parsed),
        preview_only=False,
        root=paths.root,
    )

    return set_beat_prose(model_type, beat.id, outcome.rendered or "", source="ai", root=root)


# ── Structure edits ─────────────────────────────────────────────────────


def set_emphasis(
    model_type: str,
    beat_id: str,
    *,
    node_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    loop_ids: list[str] | None = None,
    root: Path | None = None,
) -> tuple[StoryBeat, str]:
    """Set a beat's emphasis. Loop IDs expand into member node/edge IDs and
    are unioned with any explicitly-picked nodes/edges."""
    paths = require_project(root)
    store = load_story(root=root)
    doc = _find_doc(store, model_type)
    beat = _find_beat(doc, beat_id)

    loops = list(loop_ids or [])
    ln, le = _expand_loops(model_type, loops, root=paths.root)
    beat.emphasis = StoryEmphasis(
        node_ids=list(dict.fromkeys(list(node_ids or []) + ln)),
        edge_ids=list(dict.fromkeys(list(edge_ids or []) + le)),
        loop_ids=loops,
    )
    doc.updated_at = now_utc()
    sha = _save(store, subject=f"Story: set emphasis ({beat.kind})", root=root)
    return beat, sha


def reorder_beats(
    model_type: str,
    ordered_beat_ids: list[str],
    *,
    root: Path | None = None,
) -> tuple[StoryDoc, str]:
    """Reorder a doc's beats to match the given ID order (unknown IDs ignored;
    any beats omitted from the list keep their relative order at the end)."""
    store = load_story(root=root)
    doc = _find_doc(store, model_type)
    by_id = {b.id: b for b in doc.beats}
    new_order: list[StoryBeat] = []
    for bid in ordered_beat_ids:
        beat = by_id.pop(bid, None)
        if beat is not None:
            new_order.append(beat)
    new_order.extend(by_id.values())  # leftovers keep original order
    doc.beats = new_order
    doc.updated_at = now_utc()
    sha = _save(store, subject=f"Story: reorder beats ({model_type})", root=root)
    return doc, sha
