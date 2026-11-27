"""The workflow structure: stages, their steps, and the tracks that run alongside them.

One list that every surface reads, so the CLI, the server, reports, help and anything built on latris group
work the same way. Design and placement rules: ``docs/engineering/WORKFLOW_STRUCTURE.md``.

- A **stage** is a phase of modelling, in order.
- A **step** is a part of one stage.
- A **track** runs alongside every stage: what can happen at any point (citing a source, saving a version).

Everything a person or an agent can invoke sits at exactly one *place*: a step, a stage as a whole, a track,
or :data:`COMPOSITE` (an action that carries out several placed actions in one call). Nothing else in the
package spells a stage or step name; read them from here.

A surface built on latris may add steps of its own under a stage with :func:`register_step` (an editor's
presentation formats under Communicate, say). It may not add stages or tracks.
"""

from __future__ import annotations

from pydantic import Field

from latris.schema._base import SchemaModel

COMPOSITE = "composite"


class Step(SchemaModel):
    """A part of one stage. ``id`` is ``<stage>.<step>``."""

    id: str
    name: str
    description: str


class Stage(SchemaModel):
    """A phase of modelling, with its steps in order."""

    id: str
    name: str
    description: str
    steps: list[Step] = Field(default_factory=list)


class Track(SchemaModel):
    """Work that can happen at any stage."""

    id: str
    name: str
    description: str


class WorkflowStructure(SchemaModel):
    """The whole structure, as surfaces receive it (``latris capabilities``, ``GET /api/workflow``)."""

    stages: list[Stage]
    tracks: list[Track]
    composite: str = COMPOSITE


def _stage(stage_id: str, name: str, description: str, *steps: tuple[str, str, str]) -> Stage:
    return Stage(
        id=stage_id,
        name=name,
        description=description,
        steps=[Step(id=f"{stage_id}.{sid}", name=sname, description=sdesc) for sid, sname, sdesc in steps],
    )


_STAGES: list[Stage] = [
    _stage(
        "frame",
        "Frame",
        "What the model is for: the question, who reads the answer, which model types.",
        ("question", "Question and scope", "The question, the decision it informs, and the boundary."),
        ("audience", "Audience", "Who reads the result and what they will push on."),
        ("model_type", "Model type selection", "Which model types, and why."),
    ),
    _stage(
        "build",
        "Build",
        "The shared map every model type is drawn from.",
        (
            "structure",
            "Structure",
            "Factors, links, polarity, descriptions, and which elements each model type includes.",
        ),
    ),
    _stage(
        "formalise",
        "Formalise",
        "A model type's own content: what each element is, its numbers and their uncertainty.",
        ("definitions", "Definitions", "Which elements a model type has, what kind each is, and model-wide settings."),
        ("values", "Values", "Quantities on elements: probabilities, tables, equations, payoffs, weights, ratings."),
        ("ranges", "Ranges", "How uncertain each value is, and correlations between values."),
        ("scenarios", "Scenarios", "Named sets of alternative values."),
    ),
    _stage(
        "analyse",
        "Analyse",
        "Results computed from the model and recorded.",
        (
            "structural",
            "Structural analysis",
            "What the model's shape implies, with no values: loops, paths, identification.",
        ),
        ("base_case", "Base-case analysis", "The model's result from the values as set."),
        ("options", "Option comparison", "Which of the options a person could choose is better."),
        (
            "uncertainty",
            "Uncertainty analysis",
            "How uncertain the result is (including what health economics calls probabilistic sensitivity analysis).",
        ),
        ("sensitivity", "Sensitivity analysis", "Which inputs drive the result."),
        ("estimation", "Estimation from data", "What a dataset says about an effect."),
    ),
    _stage(
        "interpret",
        "Interpret",
        "What the results mean.",
        ("findings", "Findings", "Claims the results support."),
        (
            "interpretation",
            "Interpretation",
            "The written sections: the answer, confidence, limits and open questions.",
        ),
    ),
    _stage(
        "communicate",
        "Communicate",
        "The model handed to people who read it.",
        ("report", "Report", "The report and its exports."),
        ("diagram", "Diagram", "The model's picture."),
        ("sharing", "Sharing", "Links to a model and copies of it, including the model as a file."),
    ),
    _stage(
        "use",
        "Use",
        "The model called by code.",
        ("contract", "Contract", "The model's inputs and outputs, pinned to a version."),
        ("prediction", "Prediction", "Outputs for given inputs, from code or a pipeline."),
    ),
]

TRACKS: tuple[Track, ...] = (
    Track(
        id="ai",
        name="AI assistance",
        description="AI proposals and chains, and checkpoints: where an AI building a model stops to ask the person.",
    ),
    Track(
        id="evidence",
        name="Evidence",
        description="Sources, citations, source checks, extracts and provenance records.",
    ),
    Track(id="data", name="Data", description="Datasets themselves: upload, cleaning and versions."),
    Track(
        id="review",
        name="Review and challenge",
        description="A person's judgment of the work: challenges, maturity, review packs and sign-offs.",
    ),
    Track(
        id="validation",
        name="Verification and validation",
        description="Tests of the model against a "
        "criterion: well-formedness, readiness, units, fit to data, refutation.",
    ),
    Track(
        id="versions", name="Versions and history", description="Milestones, alternatives, undo and comparing versions."
    ),
    Track(
        id="project",
        name="Project",
        description="Everything that is not modelling: projects, access and "
        "sync, display and layout, reference and help.",
    ),
)

STAGE_IDS: tuple[str, ...] = tuple(s.id for s in _STAGES)
TRACK_IDS: tuple[str, ...] = tuple(t.id for t in TRACKS)
_CORE_STEP_IDS: frozenset[str] = frozenset(step.id for s in _STAGES for step in s.steps)


def stages() -> list[Stage]:
    """Every stage with its steps (latris's and any a surface registered), in order."""
    return [s.model_copy(deep=True) for s in _STAGES]


def structure() -> WorkflowStructure:
    return WorkflowStructure(stages=stages(), tracks=list(TRACKS))


def stage(stage_id: str) -> Stage:
    for s in _STAGES:
        if s.id == stage_id:
            return s
    raise KeyError(f"no stage {stage_id!r}; stages are {', '.join(STAGE_IDS)}")


def step(step_id: str) -> Step:
    for s in _STAGES:
        for st in s.steps:
            if st.id == step_id:
                return st
    raise KeyError(f"no step {step_id!r}")


def step_ids(stage_id: str | None = None) -> tuple[str, ...]:
    """Every step id in order (of one stage, or all)."""
    return tuple(st.id for s in _STAGES if stage_id is None or s.id == stage_id for st in s.steps)


def stage_of(place: str) -> str | None:
    """The stage a step or stage id belongs to; None for a track or a composite."""
    head = place.split(".", 1)[0]
    return head if head in STAGE_IDS else None


def is_place(place: str) -> bool:
    """A step, a stage, a track or :data:`COMPOSITE`."""
    if place == COMPOSITE or place in STAGE_IDS or place in TRACK_IDS:
        return True
    return any(st.id == place for s in _STAGES for st in s.steps)


def require_step(place: str, stage_id: str) -> str:
    """``place`` if it is a step of ``stage_id``; else a ValueError naming the steps it could be."""
    if place not in step_ids(stage_id):
        raise ValueError(f"{place!r} is not a step of {stage_id}; use one of {', '.join(step_ids(stage_id))}")
    return place


def register_step(stage_id: str, step_id: str, name: str, description: str) -> Step:
    """Add a step of a surface's own under an existing stage (latris's own steps can't be redefined).

    ``step_id`` is the part after the stage (``"story"`` gives ``"communicate.story"``). Registering the same
    step again with the same name and description is a no-op, so plugin loading can repeat safely.
    """
    target = stage(stage_id)
    full = f"{stage_id}.{step_id}"
    if full in _CORE_STEP_IDS:
        raise ValueError(f"{full!r} is one of latris's own steps")
    new = Step(id=full, name=name, description=description)
    for existing in target.steps:
        if existing.id == full:
            if existing != new:
                raise ValueError(f"step {full!r} is already registered differently")
            return existing
    target.steps.append(new)
    return new


def _unregister_step(step_id: str) -> None:
    """Tests only: remove a surface-registered step."""
    if step_id in _CORE_STEP_IDS:
        raise ValueError("latris's own steps can't be removed")
    s = stage(step_id.split(".", 1)[0])
    s.steps[:] = [st for st in s.steps if st.id != step_id]


__all__ = [
    "COMPOSITE",
    "STAGE_IDS",
    "TRACKS",
    "TRACK_IDS",
    "Stage",
    "Step",
    "Track",
    "WorkflowStructure",
    "is_place",
    "register_step",
    "require_step",
    "stage",
    "stage_of",
    "stages",
    "step",
    "step_ids",
    "structure",
]
