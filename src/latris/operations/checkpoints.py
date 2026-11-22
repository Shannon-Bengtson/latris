"""Checkpoints — where an AI building a model stops and asks the person.

Five checkpoints follow the modelling phases (Build → Formalise → Analyse → Interpret → Communicate):

- ``framing`` — the decision the model informs, who reads it, what the person expects the answer to be;
- ``structure`` — once the map is connected: what's missing, which factors they can change, the
  least-supported link;
- ``values`` — once values are set: the few estimates the answer is most sensitive to;
- ``surprise`` — once a result is in: does it match what the person expected?
- ``audience`` — before the report is written: the right reader, and what they'll push on.

The GUI's phase gates (``readiness.py``) check structure; checkpoints check that the person has had a
say. They never refuse anything: an open checkpoint is advice an agent shows the person, closed by
recording their answers (``record_input``), an explicit skip (``skip_checkpoint``), or the person asking
the agent to just build (``set_pace``). Questions come from the model itself — named factors, links and
values — because an agent skips generic questions it thinks it can guess.

Checkpoints apply to AI-built models only: when most factors were added by a person, none opens.
Reads never write. See latris-app ``docs/design/CHAT_CHECKPOINTS.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from latris.operations._actor import author as _author
from latris.operations.commit import RECORDED_BY_AGENT_ENV, auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model, load_model_or_default
from latris.schema import (
    CHECKPOINT_ORDER,
    CheckpointId,
    PersonInput,
    PersonInputLog,
    ProjectFoundation,
    Substrate,
    new_id,
)
from latris.schema.person_input import Pace

MAX_QUESTIONS = 3
_MIN_AI_FACTORS = 3  # the structure checkpoint waits for a map worth showing
_STALE_GROWTH = 0.5  # a reviewed structure reopens when AI factors grow by half again (and by ≥3)

PHASE: dict[str, str] = {
    "framing": "before building",
    "structure": "Build → Formalise",
    "values": "Formalise → Analyse",
    "surprise": "Analyse → Interpret",
    "audience": "Interpret → Communicate",
}

WHY: dict[str, str] = {
    "framing": "Only the person knows the decision this informs and what they expect; the report opens with it "
               "and compares their expectation with the model's answer.",
    "structure": "A map built without the person is a literature summary. They know what's missing, and which "
                 "factors they can actually change.",
    "values": "These estimates drive the answer. A number the person has checked is worth more than one the AI "
              "chose.",
    "surprise": "Where the model and the person disagree is where one of them learns something; the answer "
                "feeds the interpretation's confidence and open questions.",
    "audience": "The interpretation is written for one reader; getting them wrong wastes the writing.",
}

State = Literal["open", "answered", "skipped", "not_reached", "not_needed", "not_asked"]


@dataclass(frozen=True)
class Checkpoint:
    """An open checkpoint: what to ask the person now."""

    id: CheckpointId
    phase: str
    why: str
    questions: list[str]
    before_asking: str | None = None  # a step to take first (e.g. run a sensitivity analysis)
    covers: list[str] = field(default_factory=list)
    then: str | None = None  # what to do with the answers, besides recording them
    how: str = (
        "Ask the person these in one message and end your turn. Record their answers, in their words, with "
        "`latris checkpoint record`. If they'd rather you carry on without them, skip it with "
        "`latris checkpoint skip` (say why), or `latris checkpoint pace just-build` for the rest of the model."
    )


@dataclass(frozen=True)
class CheckpointStatus:
    """Where one checkpoint stands."""

    id: CheckpointId
    phase: str
    state: State
    entry: PersonInput | None = None  # the latest record, when answered or skipped


@dataclass(frozen=True)
class CheckpointReport:
    pace: Pace
    open: Checkpoint | None
    checkpoints: list[CheckpointStatus]


# ── Reading the model ─────────────────────────────────────────────────────


@dataclass
class _Model:
    paths: Any
    foundation: ProjectFoundation
    substrate: Substrate
    log: PersonInputLog
    labels: dict[str, str]
    ai_entities: list[str]
    ai_built: bool

    def latest(self, checkpoint: str) -> PersonInput | None:
        for e in reversed(self.log.entries):
            if e.checkpoint == checkpoint:
                return e
        return None


def _load(root: Path | None) -> _Model:
    paths = require_project(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    log = load_model_or_default(PersonInputLog, paths.person_input_yaml)
    ai = [e.id for e in substrate.entities if e.origin == "ai-proposed"]
    # Built by an AI: no factors yet (nothing a person did to respect), or most of them AI-proposed.
    ai_built = not substrate.entities or len(ai) * 2 >= len(substrate.entities)
    return _Model(
        paths=paths,
        foundation=foundation,
        substrate=substrate,
        log=log,
        labels={e.id: e.label for e in substrate.entities},
        ai_entities=ai,
        ai_built=ai_built,
    )


def _quoted(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _listing(labels: list[str]) -> str:
    quoted = [f"'{x}'" for x in labels]
    if len(quoted) <= 1:
        return "".join(quoted)
    return ", ".join(quoted[:-1]) + " and " + quoted[-1]


def _outcomes(m: _Model) -> list[str]:
    from latris.operations import formalisms

    ids: set[str] = set()
    for t in m.foundation.selected_model_types or ["cld"]:  # an unselected project is a loop map
        f = formalisms.get(t)
        if f is not None:
            try:
                ids |= f.outcome_ids(m.paths)
            except (OSError, ValueError):
                continue
    return [i for i in ids if i in m.labels]


def _results(m: _Model) -> list[Any]:
    """Recorded analysis runs the report shows, newest first."""
    from latris.operations.analysis_results import list_results

    return [run for run, hidden, _stale in list_results(root=m.paths.root) if not hidden]


def _findings(m: _Model) -> list[Any]:
    from latris.operations.findings import iter_findings

    return list(iter_findings(root=m.paths.root))


# ── The five checkpoints ──────────────────────────────────────────────────
# Each returns None when it isn't reached yet, else the Checkpoint to ask (its questions built from the model).


def _framing(m: _Model) -> Checkpoint | None:
    f = m.foundation
    missing = []
    if not f.background.strip():
        missing.append("What's happening, and what decision will this model inform?")
    if not f.audience.strip():
        missing.append("Who will read the result — a board, a funder, your team?")
    if not f.predictions.strip():
        question = (f.statement or "the question").strip().rstrip("?")
        missing.append(f"Before I build: what do you expect the answer to '{_quoted(question, 120)}' to be?")
    if not missing:
        return None  # all three on record: nothing left to frame
    return Checkpoint("framing", PHASE["framing"], WHY["framing"], missing[:MAX_QUESTIONS],
                      then="Put the answers in the project too (`latris project set background|audience|predictions "
                           "\"...\"`) — the report opens with them.")


def _structure(m: _Model) -> Checkpoint | None:
    from latris.operations.readiness import _assess_build_to_formalise

    if len(m.ai_entities) < _MIN_AI_FACTORS:
        return None
    if _assess_build_to_formalise(m.paths).light != "green":
        return None
    edges = [e for e in m.substrate.edges if e.from_id in m.labels and e.to_id in m.labels]
    degree: dict[str, int] = {i: 0 for i in m.labels}
    for e in edges:
        degree[e.from_id] += 1
        degree[e.to_id] += 1
    outcomes = _outcomes(m)
    top = sorted(m.labels, key=lambda i: (-degree[i], m.labels[i]))[:6]
    around = f" around {_listing([m.labels[o] for o in outcomes])}" if outcomes else ""
    questions = [
        f"I've mapped {len(m.labels)} factors and {len(edges)} links{around}, mainly "
        f"{_listing([m.labels[i] for i in top])}. Is anything important missing, or anything here that "
        "shouldn't be?"
    ]
    drivers = sorted({e.from_id for e in edges if e.to_id in outcomes and e.from_id not in outcomes},
                     key=lambda i: (-degree[i], m.labels[i]))[:5]
    if drivers:
        questions.append(f"Which of {_listing([m.labels[i] for i in drivers])} can you actually change or "
                         "influence?")
    elif not outcomes:
        questions.append("Which factor is the outcome you care about, and which can you change or influence?")
    weak = _weakest_link(m, edges)
    if weak:
        questions.append(weak)
    return Checkpoint("structure", PHASE["structure"], WHY["structure"], questions[:MAX_QUESTIONS],
                      covers=sorted(m.ai_entities),
                      then="Change the map as they say: add what's missing, remove what isn't so, and log a "
                           "decision (`latris decision log`) for anything you keep that they doubted.")


def _weakest_link(m: _Model, edges: list[Any]) -> str | None:
    from latris.schema import ConfidenceSet, EvidenceLinkSet, PolaritySet

    paths = m.paths
    evidence = load_model_or_default(EvidenceLinkSet, paths.evidence_links_yaml).entries
    sourced = {e.target_id for e in evidence if e.stance == "for"}
    confidence = {c.target_id: c.value for c in load_model_or_default(ConfidenceSet, paths.confidence_yaml).entries}
    polarity_path = paths.view_attribute_path("cld", "polarity")
    polarity = {p.target_id: p.value for p in load_model_or_default(PolaritySet, polarity_path).entries}
    rank = {"low": 0, "medium": 1, "high": 2}
    causal = [e for e in edges if e.origin == "ai-proposed"]
    if not causal:
        return None
    weakest = min(causal, key=lambda e: (e.id in sourced, rank.get(confidence.get(e.id, ""), 1),
                                         m.labels[e.from_id], m.labels[e.to_id]))
    a, b = m.labels[weakest.from_id], m.labels[weakest.to_id]
    sign = polarity.get(weakest.id)
    reading = {"+": f" (more {a}, more {b})", "-": f" (more {a}, less {b})"}.get(str(sign), "")
    support = "it has no source yet" if weakest.id not in sourced else "it's the link I'm least sure of"
    return f"Is '{a} → {b}'{reading} right? {support[0].upper()}{support[1:]}."


def _quantified(m: _Model) -> list[Any]:
    """The model's types that aren't the causal map itself — the selected ones, or any registered one when
    nothing is selected (values can be set before a type is chosen)."""
    from latris.operations import formalisms

    chosen = [formalisms.get(t) for t in m.foundation.selected_model_types] or formalisms.all_formalisms()
    return [f for f in chosen if f is not None and not f.whole_map]


def _values_set(m: _Model) -> bool:
    """Some type has values set (rates, probabilities, scores)."""
    for f in _quantified(m):
        if f.spec_export is None:
            continue
        try:
            if f.spec_export(m.paths, m.labels):
                return True
        except (OSError, ValueError, KeyError):
            continue
    return False


def _sensitivity_tools(m: _Model) -> list[str]:
    tools = []
    for f in _quantified(m):
        try:
            if not (f.spec_export and f.spec_export(m.paths, m.labels)):
                continue
        except (OSError, ValueError, KeyError):
            continue
        for rk in f.results:
            if "sensitivity" in rk.analysis and rk.tool is not None:
                tools.append(rk.tool.name)
    return tools


def _values(m: _Model) -> Checkpoint | None:
    if not _values_set(m):
        return None
    from latris.operations.analysis_results import load_payload

    runs = [r for r in _results(m) if r.purpose == "sensitivity-analysis"]
    questions: list[str] = []
    for run in runs[:2]:
        payload = load_payload(run, root=m.paths.root) or {}
        questions += _value_questions(payload)
        if len(questions) >= MAX_QUESTIONS:
            break
    if questions:
        return Checkpoint("values", PHASE["values"], WHY["values"], questions[:MAX_QUESTIONS], then=_VALUES_THEN)
    tools = _sensitivity_tools(m)
    first = (
        f"Run its sensitivity analysis ({' or '.join(sorted(set(tools)))}) to find the values that move the "
        "answer most, then ask about the 2–3 of those you estimated yourself."
        if tools else
        "Pick the 2–3 values that most decide the answer and that you estimated yourself, and ask about those."
    )
    return Checkpoint(
        "values", PHASE["values"], WHY["values"],
        ["Which of the values I've set do you know better than my estimates — a rate, a probability, a cost or "
         "a weight? (I'll name the ones that matter most.)"],
        before_asking=first,
        then=_VALUES_THEN,
    )


_VALUES_THEN = ("Set each value the person gives you, and add an assumption (`latris assumption add`) for any they "
                "couldn't — so the report shows which numbers are still estimates.")


def _value_questions(payload: dict[str, Any]) -> list[str]:
    """Questions about the estimates a recorded sensitivity result ranks highest (unchecked ones only).

    Reads the two payload shapes sensitivity results have: rows of values swung low/high (``parameters``)
    and probability-table cells (``findings``).
    """
    out: list[str] = []
    for row in payload.get("parameters") or []:
        if row.get("swing") in (None, 0) or not row.get("weak"):
            continue
        units = f" {row['units']}" if row.get("units") else ""
        out.append(f"'{row.get('label')}' is {row.get('baseline_value')}{units} — my estimate, and one of the "
                   "values the result moves with most. Is that right, or what would you put?")
    labels = payload.get("labels") or {}
    for cell in payload.get("findings") or []:
        if not cell.get("weak") or not cell.get("influence"):
            continue
        node = labels.get(cell.get("node_id"), cell.get("node_id"))
        given = ", ".join(f"{labels.get(k, k)} = {v}" for k, v in (cell.get("parent_states") or {}).items())
        prob = cell.get("baseline_prob")
        pct = f"{prob:.0%}" if isinstance(prob, int | float) else str(prob)
        out.append(f"The chance of '{node} = {cell.get('state')}'{' when ' + given if given else ''} is {pct} — "
                   "my estimate, and the answer is among the most sensitive to it. Does that sound right?")
    return out


def _surprise(m: _Model) -> Checkpoint | None:
    expected = m.foundation.predictions.strip()
    if not expected:
        return None
    headline = next((r.output_summary for r in _results(m) if r.output_summary.strip()), "")
    if not headline:
        headline = next((f.statement for f in _findings(m) if getattr(f, "statement", "").strip()), "")
    if not headline:
        return None
    return Checkpoint(
        "surprise", PHASE["surprise"], WHY["surprise"],
        [f"You expected: “{_quoted(expected)}”. So far the model says: {_quoted(headline)}. Does that match what "
         "you see? If not, what's different?"],
        then="Carry what they say into the interpretation — its confidence and open questions "
             "(`latris interpret set-prose`).",
    )


def _audience(m: _Model) -> Checkpoint | None:
    if not (_results(m) or _findings(m)):
        return None
    reader = m.foundation.audience.strip()
    who = f"'{_quoted(reader, 120)}'" if reader else "a reader you haven't named yet"
    return Checkpoint(
        "audience", PHASE["audience"], WHY["audience"],
        [f"I'm about to write the report for {who}. Is that the right reader, and what will they push back on "
         "or need to see?"],
    )


_BUILDERS = {
    "framing": _framing,
    "structure": _structure,
    "values": _values,
    "surprise": _surprise,
    "audience": _audience,
}


def _stale(entry: PersonInput, m: _Model) -> bool:
    """An answered structure review covers the map it saw; it reopens once the AI has grown that map a lot."""
    if entry.checkpoint != "structure" or entry.outcome != "answered" or not entry.covers:
        return False
    new = set(m.ai_entities) - set(entry.covers)
    return len(new) >= max(3, _STALE_GROWTH * len(entry.covers))


def _status(cid: CheckpointId, m: _Model) -> tuple[CheckpointStatus, Checkpoint | None]:
    entry = m.latest(cid)
    if entry is not None and not _stale(entry, m):
        return CheckpointStatus(cid, PHASE[cid], entry.outcome, entry), None
    if not m.ai_built:
        return CheckpointStatus(cid, PHASE[cid], "not_needed"), None
    checkpoint = _BUILDERS[cid](m)
    if checkpoint is None:
        return CheckpointStatus(cid, PHASE[cid], "not_reached" if cid != "framing" else "not_needed"), None
    if m.log.pace == "just_build":
        return CheckpointStatus(cid, PHASE[cid], "not_asked"), None
    return CheckpointStatus(cid, PHASE[cid], "open"), checkpoint


def checkpoint_report(*, root: Path | None = None) -> CheckpointReport:
    """Every checkpoint's state, and the one to ask now (the first open one in phase order)."""
    m = _load(root)
    statuses: list[CheckpointStatus] = []
    first: Checkpoint | None = None
    for cid in CHECKPOINT_ORDER:
        status, checkpoint = _status(cid, m)
        statuses.append(status)
        if first is None and checkpoint is not None:
            first = checkpoint
    return CheckpointReport(pace=m.log.pace, open=first, checkpoints=statuses)


def open_checkpoint(*, root: Path | None = None) -> Checkpoint | None:
    """The checkpoint to ask the person about now, or None."""
    return checkpoint_report(root=root).open


# ── Recording ─────────────────────────────────────────────────────────────


def _record(entry_kwargs: dict[str, Any], subject: str, m: _Model) -> tuple[PersonInput, str]:
    entry = PersonInput(
        id=new_id("person-input"),
        relayed_by=os.environ.get(RECORDED_BY_AGENT_ENV) or None,
        authored_by=_author(m.paths.root),
        **entry_kwargs,
    )
    m.log.entries.append(entry)
    dump_model(m.log, m.paths.person_input_yaml)
    sha = auto_commit(m.paths.root, subject=subject, body=f"id: {entry.id}", paths=[m.paths.person_input_yaml])
    return entry, sha


def _current_questions(cid: CheckpointId, m: _Model) -> tuple[list[str], list[str]]:
    checkpoint = _BUILDERS[cid](m) if m.ai_built else None
    return (checkpoint.questions, checkpoint.covers) if checkpoint else ([], [])


def record_input(
    checkpoint: CheckpointId,
    answers: str,
    *,
    questions: list[str] | None = None,
    root: Path | None = None,
) -> tuple[PersonInput, str]:
    """Record the person's answers at a checkpoint, in their words. ``questions`` defaults to what the
    checkpoint asks now."""
    if checkpoint not in CHECKPOINT_ORDER:
        raise ValueError(f"checkpoint must be one of {', '.join(CHECKPOINT_ORDER)}")
    if not answers.strip():
        raise ValueError("Give the person's answers, in their words.")
    m = _load(root)
    asked, covers = _current_questions(checkpoint, m)
    return _record(
        {"checkpoint": checkpoint, "outcome": "answered", "questions": questions or asked,
         "answers": answers.strip(), "covers": covers},
        f"Person input at {checkpoint}: {_quoted(answers, 60)}",
        m,
    )


def skip_checkpoint(
    checkpoint: CheckpointId, reason: str, *, root: Path | None = None
) -> tuple[PersonInput, str]:
    """Carry on past a checkpoint without the person; the report shows it was skipped, and why."""
    if checkpoint not in CHECKPOINT_ORDER:
        raise ValueError(f"checkpoint must be one of {', '.join(CHECKPOINT_ORDER)}")
    if not reason.strip():
        raise ValueError("Say why the checkpoint is skipped (e.g. 'the person asked me to just build').")
    m = _load(root)
    asked, covers = _current_questions(checkpoint, m)
    return _record(
        {"checkpoint": checkpoint, "outcome": "skipped", "questions": asked, "reason": reason.strip(),
         "covers": covers},
        f"Skipped checkpoint {checkpoint}: {_quoted(reason, 60)}",
        m,
    )


def set_pace(pace: Pace, *, root: Path | None = None) -> tuple[PersonInputLog, str]:
    """``just_build``: the person asked the agent to carry on without them — no checkpoint opens again, and
    the report says which were never asked. ``ask``: checkpoints open again."""
    if pace not in ("ask", "just_build"):
        raise ValueError("pace must be 'ask' or 'just_build'")
    m = _load(root)
    m.log.pace = pace
    dump_model(m.log, m.paths.person_input_yaml)
    subject = ("Person asked to just build: checkpoints off" if pace == "just_build"
               else "Checkpoints back on: ask the person")
    sha = auto_commit(m.paths.root, subject=subject, paths=[m.paths.person_input_yaml])
    return m.log, sha
