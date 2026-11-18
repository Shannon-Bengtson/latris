"""Formalism plugins — everything one model type adds, registered in one module.

A model type built on the shared substrate needs the same dozen hooks:
readiness validators, how it treats an "outcome", its interpretation claims,
its recorded result kinds (report renderer, analysis replay), its block in a
build spec (check, apply, export for share links), its diagram, and its CLI
and server modules. Rather than a branch for each type in a dozen files,
each type declares a :class:`Formalism` in its own module here, and the
shared code reads :data:`FORMALISMS`.

Adding a type: register its :class:`~latris.schema.model_types.ModelTypeSpec`
(schema), its foundations entry (``operations/foundations.py``), its help
topic (``server/help.py``) and its build-spec block (``schema/build_spec.py``,
a static pydantic field), then write one module here and add it to the
imports at the bottom. ``tests/operations/test_formalisms.py`` checks every
stable type is fully wired.

The older types (CLD, DAG, FCM, SD) predate this and keep their own
wiring; they aren't registered here yet (BN was the first to move).

Hooks import their operations lazily, so importing this package is cheap and
can't create import cycles.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Claims = Callable[[Any, str], list[str]]  # (paths, section) → claims; sections below
CLAIM_SECTIONS = ("structure", "answer", "gaps", "implications", "sensitivity")


@dataclass(frozen=True)
class ResultKind:
    """A recorded analysis a formalism produces, and how reports and links handle it."""

    kind: str  # ``AnalysisRun.result_kind``, e.g. "ft-analysis"
    title: str  # heading in the report's Results section
    render: Callable[[dict[str, Any]], list[str]]  # payload → Markdown lines
    analysis: str  # the build-spec ``SpecAnalysis.kind`` that runs it, e.g. "ft_analyse"
    run: Callable[[Any, Path], str]  # (SpecAnalysis, root) → run id; runs and records it
    definition: Callable[[dict[str, Any]], Any]  # recorded payload → SpecAnalysis that reproduces it
    # (payload, claims by interpretation section) → add this result's claims, e.g. to "answer_to_question"
    claims: Callable[[dict[str, Any], dict[str, list[str]]], None] | None = None
    # payload → [(chart kind, extra keys)] for the report's ``latris-chart`` markers; the app draws them.
    # Chart kinds are namespaced per formalism ("mcda-swing") so each app renderer owns its contract.
    charts: Callable[[dict[str, Any]], list[tuple[str, dict[str, Any]]]] | None = None
    # The most runs of this kind a report shows (default 4) — e.g. a BN query per evidence set.
    report_limit: int | None = None
    # payload → what this run was of, for its heading ("given Hot week = yes"), so repeated
    # headings say which run is which.
    subtitle: Callable[[dict[str, Any]], str] | None = None
    # Every chart kind ``charts`` may emit, declared so surfaces that draw them (the app) can be checked
    # against the library without running anything. Required when ``charts`` is set.
    chart_kinds: tuple[str, ...] = ()
    # The run reads a dataset (``latris data``), not only the model: a share link can't re-run it.
    needs_dataset: bool = False
    # ``definition`` also needs the run's hyperparameters (e.g. SD's clock and saved scenario names, which
    # older payloads don't hold): it is then called as ``definition(payload, hyperparameters)``.
    definition_reads_run: bool = False
    # payload → the result's heading, when it depends on the run ("Sensitivity of PM2.5 Load"); else ``title``.
    title_for: Callable[[dict[str, Any]], str] | None = None


@dataclass(frozen=True)
class Analysis:
    """An analysis layer on an existing model type — e.g. effect estimation on a DAG.

    Not a model type of its own: it adds a recorded result kind to ``model_type`` (which may be one of the
    older types not registered as a :class:`Formalism`).
    """

    model_type: str
    result: ResultKind
    fingerprint_files: Callable[[Any], list[Path]] | None = None  # extra inputs its results depend on


@dataclass(frozen=True)
class Formalism:
    model_type: str

    # ── outcome of interest ──
    # The role an "outcome" becomes in this formalism (a spec's ``outcome:``), or None if it has no single
    # outcome; ``outcome_refusal`` is what someone asking for an "outcome" role is told.
    outcome_role: str | None
    outcome_refusal: str
    outcome_ids: Callable[[Any], set[str]]  # paths → ids of the outcome(s) of interest
    set_outcome: Callable[[str, Path], Any] | None = None  # (target, root): give the outcome its role

    # ── readiness ──
    structure_problems: Callable[[Path], list[Any]] | None = None  # root → problems (target_id, gap_type, message)
    validators: dict[str, tuple[str, ...]] = field(default_factory=dict)  # validator name → gap types it reports
    whole_label: str = "(model)"  # how a problem about the whole model is labelled

    # ── interpretation ──
    claims: Claims | None = None
    centrality: bool = True  # do generic graph-centrality claims mean anything here?
    own_implications: bool = False  # implications come from ``claims`` instead of centrality
    sensitivity_fallback: str | None = None  # set: sensitivity comes only from ``claims`` (else this text)

    # ── results ──
    results: tuple[ResultKind, ...] = ()
    fingerprint_files: Callable[[Any], list[Path]] | None = None  # extra inputs a result depends on

    # ── build spec and share links ──
    spec_field: str | None = None  # the ``BuildSpec`` field holding this formalism's block
    spec_check: Callable[[Any, Callable[[str], bool], str | None], list[str]] | None = None  # (block, known, outcome)
    spec_apply: Callable[[Any, str, Path], int] | None = None  # (block, verified_by, root) → values set
    spec_export: Callable[[Any, dict[str, str]], Any] | None = None  # (paths, labels) → block or None

    # ── diagram ──
    mermaid: Callable[[Any, list, list], str] | None = None  # (paths, entities, edges) → full source, or ""
    mermaid_groups: Callable[[Any], tuple[list[str], dict[str, str], dict[str, str]]] | None = None
    # ↑ paths → (group order, group names, entity id → group): columns for the generic diagram

    # ── surfaces (module paths; the CLI and server layers import them) ──
    cli: tuple[str, str] | None = None  # (module, command name), e.g. ("latris.cli.ft_cmd", "ft")
    routes: str | None = None  # module with a FastAPI ``router``


FORMALISMS: dict[str, Formalism] = {}
ANALYSES: list[Analysis] = []


def _check_declared(new: list[ResultKind]) -> None:
    for r in new:
        if bool(r.charts) != bool(r.chart_kinds):
            raise ValueError(f"result kind {r.kind!r}: declare chart_kinds exactly when it has a charts hook")


def _refuse_clash(new: list[ResultKind]) -> None:
    kinds = {r.kind for r in result_kinds()}
    analyses = {r.analysis for r in result_kinds()}
    clash = (kinds & {r.kind for r in new}) | (analyses & {r.analysis for r in new})
    if clash:
        raise ValueError(f"result or analysis kind(s) {sorted(clash)} already registered")


def register(f: Formalism) -> Formalism:
    if f.model_type in FORMALISMS:
        raise ValueError(f"formalism {f.model_type!r} registered twice")
    _check_declared(list(f.results))
    _refuse_clash(list(f.results))
    FORMALISMS[f.model_type] = f
    return f


def register_analysis(a: Analysis) -> Analysis:
    _check_declared([a.result])
    _refuse_clash([a.result])
    ANALYSES.append(a)
    return a


def get(model_type: str | None) -> Formalism | None:
    return FORMALISMS.get(model_type) if model_type else None


def all_formalisms() -> list[Formalism]:
    return list(FORMALISMS.values())


def _owned() -> list[tuple[str, ResultKind]]:
    """Every registered result kind with the model type it belongs to — formalisms first, then analyses."""
    return [(f.model_type, r) for f in FORMALISMS.values() for r in f.results] + [
        (a.model_type, a.result) for a in ANALYSES
    ]


def result_kinds() -> list[ResultKind]:
    return [r for _, r in _owned()]


def result_kind(kind: str) -> tuple[str, ResultKind] | None:
    """(model type, result kind) for a recorded ``result_kind``, or None if it isn't a registered one."""
    return next(((mt, r) for mt, r in _owned() if r.kind == kind), None)


def kind_model_types() -> dict[str, str]:
    return {r.kind: mt for mt, r in _owned()}


def fingerprint_files(model_type: str, paths: Any) -> list[Path]:
    """Inputs beyond structure, roles and parameters that this model type's results read."""
    out: list[Path] = []
    f = get(model_type)
    if f and f.fingerprint_files:
        out += f.fingerprint_files(paths)
    for a in ANALYSES:
        if a.model_type == model_type and a.fingerprint_files:
            out += a.fingerprint_files(paths)
    return out


def for_analysis(analysis: str) -> ResultKind | None:
    return next((r for r in result_kinds() if r.analysis == analysis), None)


def claims(model_type: str, paths: Any, section: str) -> list[str]:
    """This formalism's claims for one interpretation section ([] for types not registered here)."""
    f = get(model_type)
    return f.claims(paths, section) if f and f.claims else []


def problem_labels(substrate) -> dict[str, str]:
    """Entity and edge labels, for naming the element a structure problem is about."""
    labels = {e.id: e.label for e in substrate.entities}
    labels.update(
        {e.id: f"{labels.get(e.from_id, e.from_id)} → {labels.get(e.to_id, e.to_id)}" for e in substrate.edges}
    )
    return labels


def spec_verification(verified: bool, verified_by: str) -> str:
    """A spec value marked verified counts as human-verified only when a person built the spec."""
    return "human-verified" if verified and verified_by == "human" else "unverified"


def default_origin(verified_by: str) -> str:
    return "ai-proposed" if verified_by == "ai" else "human-direct"


# Registration order is the order commands, routes and report sections appear in — kept explicit here
# (not as import statements, which formatters re-sort).
_MODULES = (
    "sd", "bn",  # first: SD's then BN's results lead the report, as before they registered
    "theory_of_change", "fault_tree", "bow_tie", "event_tree", "dag_estimation", "mcda", "ach", "decision_tree",
    "markov", "toc_impact",
)


def _load() -> None:
    import importlib

    for name in _MODULES:
        importlib.import_module(f"{__name__}.{name}")


_load()
