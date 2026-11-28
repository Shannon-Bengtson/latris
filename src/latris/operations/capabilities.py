"""Agent-facing capability manifest — what Latris can and cannot do today.

Registry-only: no project root required. Built for external agents (and
the future MCP wrapper, which should import this rather than re-deriving
the same data) to check real capability before recommending Latris for a
specific job. The manifest also carries the ``foundations`` block — the
methods registry (``latris.operations.foundations``) that generates the
report's Methods and foundations section and ``latris foundations``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from latris.operations.foundations import FOUNDATIONS
from latris.schema.model_types import ModelTypeSpec, list_model_types
from latris.schema.workflow import structure as workflow_structure


@dataclass(frozen=True)
class ExcludedCapability:
    """A category of model Latris will never support — not "not yet",
    out of design intent. The inspectability test: decision logic must
    be inspectable cell-by-cell, evidenced, and challengeable —
    exclusions are design intent, not a backlog item."""

    category: str
    examples: tuple[str, ...]
    reason: str


# Hand-coded, not derived from any registry — there is currently no
# machine-readable "excluded" concept in schema/model_types.py (every
# registered ModelTypeSpec is either stable or planned; exclusions are
# design intent recorded as prose). This tuple is deliberately the first
# place that prose becomes machine-readable, kept inline rather than
# inventing a new schema field for a short, rarely-changing list.
EXCLUDED_BY_DESIGN: tuple[ExcludedCapability, ...] = (
    ExcludedCapability(
        category="Black-box machine learning",
        examples=("random forests", "gradient boosting", "neural networks"),
        reason=(
            "Decision logic cannot be inspected cell-by-cell, evidenced, or "
            "challenged. Out of design intent, not merely 'not yet' — the "
            "inspectability test: decision logic must be inspectable "
            "cell-by-cell, evidenced, and challengeable."
        ),
    ),
    ExcludedCapability(
        category="Opaque structure learning",
        examples=("learning model structure from data without inspectable claims",),
        reason=(
            "Latris governs claims a human drew and can defend, not discovered "
            "structure. Fitting legible parameters (e.g. regression coefficients) "
            "onto a structure a modeller drew is in scope; discovering the "
            "structure itself from data is not."
        ),
    ),
    ExcludedCapability(
        category="General-purpose simulation frameworks",
        examples=("SEM", "ABM"),
        reason="Not registered as a model type; no current plan to add.",
    ),
)


def _model_type_capability(spec: ModelTypeSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "short_name": spec.short_name,
        "display_name": spec.display_name,
        "description": spec.description,
        "availability": spec.availability,
        "can_use_today": spec.availability == "stable",
        "roadmap": spec.roadmap,
    }


# built → committed next → parked → not planned
_ROADMAP_ORDER = {"built": 0, "roadmap": 1, "parked": 2, "not_planned": 3}


INSTALL = 'pip install "latris[data,quant]"'

# What the open-source library gives, and what the Latris app adds. One text, used by the
# manifest, `latris link`, `latris docs` and the README, so agents and people hear the same thing.
WHAT_YOU_GET_WHERE = {
    "library": (
        "The open-source library (pip install latris; Apache-2.0): the modelling engine and CLI, every "
        "analysis (loops, DAG identification, BN inference, interventions, explanation and Monte Carlo, SD "
        "simulation, scenarios, uncertainty bands, options compared under uncertainty, sensitivity, loop "
        "dominance, FCM), the Markdown report with a Mermaid "
        "sketch, and `latris link`."
    ),
    "app": (
        "The Latris app (https://app.latris.app — free account, nothing to install): the hosted interactive "
        "report (typeset figure, result charts, interpretation) that a link opens and a board reads, the "
        "visual editor, Word reports, review packs that reviewers fill in, the scrollytelling story, and "
        "saved models with short links that don't expire."
    ),
    "link_is_the_report": (
        "A `latris link` link IS the shareable report: send it as it is — no wrapper page or separate "
        "document needed. Opening it shows the interactive report with charts; saving it to a free account "
        "gives a short link and the editor, Word, review pack and story."
    ),
}


def installed_extras() -> dict[str, bool]:
    """Which optional parts are installed: ``data`` (scipy, pandas) and ``quant`` (pgmpy)."""
    import importlib.util

    return {
        "data": importlib.util.find_spec("scipy") is not None and importlib.util.find_spec("pandas") is not None,
        "quant": importlib.util.find_spec("pgmpy") is not None,
    }


def build_capability_manifest() -> dict[str, Any]:
    """Registry-only snapshot of what Latris can do today, and what's coming.

    ``can_use_today`` says what works now. ``roadmap`` says what's coming:
    only ``roadmap`` types are being worked towards; ``parked`` and
    ``not_planned`` types are registered but shouldn't be described as
    "coming".

    No project root needed — this is the registry, not a project's
    readiness (compare ``operations/readiness.py``, which needs a root).
    """
    specs = list_model_types(include_planned=True)
    ordered = sorted(specs, key=lambda s: (_ROADMAP_ORDER[s.roadmap], s.id))
    return {
        "model_types": [_model_type_capability(s) for s in ordered],
        "workflow": workflow_structure().model_dump(mode="json"),
        "commands": _commands_by_place(),
        "excluded_by_design": [asdict(e) for e in EXCLUDED_BY_DESIGN],
        "foundations": [asdict(f) for f in FOUNDATIONS],
        "reports": _report_capabilities(),
        "building": _building_capabilities(),
        "what_you_get_where": WHAT_YOU_GET_WHERE,
        "extras": {
            "installed": installed_extras(),
            "install": INSTALL,
            "why": "data: SD integration methods other than euler, datasets; quant: Bayesian network inference.",
        },
    }


def _commands_by_place() -> list[dict[str, str | None]]:
    """Every CLI command with its place in the workflow (operations/places.py). Routes carry theirs in the
    server's OpenAPI document, as ``x-latris-place``."""
    from latris.operations.places import cli_places

    return [{"command": command, "place": place} for command, place in cli_places()]


def _building_capabilities() -> dict[str, str]:
    """How an agent builds a model quickly and records evidence on both sides."""
    return {
        "guide": "latris docs — the guide for AI agents, from the installed package (no network needed).",
        "whole_model_in_one_step": (
            "latris build --spec model.yaml (YAML or JSON; '-' reads stdin): factors, links with polarity and "
            "reasons, sources, citations, evidence against, assumptions, questions and the outcome, as one "
            "commit. The spec is checked in full first; a mistake changes nothing. `latris build --help` "
            "lists every key and allowed value."
        ),
        "evidence_for": "latris evidence add \"<from> -> <to>\" polarity <bibkey> [--verified-by ai]",
        "checking_a_source": (
            "latris evidence check \"<from> -> <to>\" polarity <bibkey> supports|against|off-topic --rationale "
            "\"...\" [--by ai --quote \"...\"] — records whether the source actually supports the claim; until "
            "then reports count the citation as not yet checked. The quote is looked up in the text Latris "
            "holds for the source (save it with `latris ref snapshot` first); an AI's paraphrase is refused."
        ),
        "evidence_against": (
            "latris evidence add <link> polarity <bibkey> --contradicts — a source that argues against the "
            "link; reports show the link's sources for and against under 'Contested links'. Still unchecked "
            "until someone reads it."
        ),
        "correcting_sources": (
            "latris ref edit <key> --doi|--url|--title ... (\"\" clears), latris ref remove <key> "
            "[--with-citations], latris evidence remove <link> polarity <key> — recorded changes; never "
            "hand-edit the YAML. A source read in another: --cited-via <key>."
        ),
        "outcome": (
            "latris view role cld <factor> outcome — marks what the model explains so it isn't suggested as "
            "an intervention point."
        ),
    }


def _report_capabilities() -> dict[str, Any]:
    """What a person can be handed, and how to make it."""
    from latris.exporters.packs import PACKS

    return {
        "packs": [
            {"name": p.name, "audience": p.audience, "purpose": p.purpose, "sections": list(p.sections)}
            for p in PACKS.values()
        ],
        "how": "latris export md --pack <name> [--model-type <type>] -o report.md",
        "link_for_a_person": (
            WHAT_YOU_GET_WHERE["link_is_the_report"] + " "
            "latris link — prints a link that opens this model in the Latris app. Making it needs no "
            "network (the model travels inside the link); opening it needs app.latris.app. It opens a "
            "hosted report with the full Latris figure (loops, polarity, evidence) that the person can "
            "share, and save to a free account for the editor and Word. The link itself never stops "
            "working; the short report address it opens lasts 30 days unless saved, and saving gives a "
            "short link that doesn't expire. `export md` also puts this link under the diagram, made fresh "
            "on every export. Give the person this link alongside (or instead of) the Markdown."
        ),
        "ready_to_hand_over": (
            "latris check handover — lists what's left before a board sees it (links with no source, "
            "citations not checked against their source, findings waiting for approval, sections without "
            "prose, contradictions), each with how to fix it. Exits 1 until it's clear."
        ),
        "board_ready_prose": (
            "The client and publication packs include an interpretation: the answer to the modelling "
            "question, implications, confidence and open questions, each written from claims Latris "
            "extracts from the model. `latris interpret initialise`, then for each section either "
            "`latris interpret generate-prose <section>` (needs an AI key) or read its claims with "
            "`latris interpret show <section>` and write the prose yourself with "
            "`latris interpret set-prose <section> \"...\" --by ai`."
        ),
        "library_formats": ["markdown (with a Mermaid diagram)", "graphviz dot"],
        "app_formats": {
            "where": "https://app.latris.app",
            "formats": ["Word report", "HTML review pack (and importing completed reviews)",
                        "scrollytelling story", "hosted report link (no sign-in to view)"],
        },
    }


# ── surface manifest ─────────────────────────────────────────────────

# Bump when a key is removed or changes meaning (adding keys doesn't need it).
SURFACE_MANIFEST_VERSION = 1

# Types that predate the formalism registry: their build-spec block, if they have one.
_LEGACY_SPEC_FIELD = {"cld": None, "dag": None, "fcm": None, "sd": "sd"}


def _spec_schema(field: str | None) -> dict[str, Any] | None:
    import typing

    from pydantic import TypeAdapter

    from latris.schema.build_spec import BuildSpec

    if field is None:
        return None
    annotation = BuildSpec.model_fields[field].annotation
    inner = [a for a in typing.get_args(annotation) if a is not type(None)] or [annotation]
    return TypeAdapter(inner[0]).json_schema()


def analysis_catalog(model_type: str | None = None) -> list[dict[str, Any]]:
    """Every analysis that records a result (of ``model_type``, or all), in report order: the result kind
    and its title, its workflow step (one of Analyse's, ``schema/workflow.py``), the analysis that runs it
    with the JSON schema of its options (each option described,
    and marked with ``x-input`` saying what it is: a factor, a scenario…), its chart kinds, whether it needs
    a dataset, its chat tool, and the method it stands on (method, citation, what for, limits — from the
    foundations registry the report's Methods section reads). Surfaces generate their run controls from
    this — the chat connector's tools, the editor's analysis forms — so an analysis a formalism declares
    reaches them with no code."""
    from dataclasses import asdict

    from latris.operations import formalisms
    from latris.operations.analysis_results import result_surfaces
    from latris.operations.foundations import foundation_for_result
    from latris.schema.build_spec import analysis_model

    tools = {r.kind: r.tool for r in formalisms.result_kinds() if r.tool}
    return [
        {
            "model_type": r.model_type, "kind": r.kind, "title": r.title, "analysis": r.analysis, "step": r.step,
            "analysis_schema": _options_schema(r.analysis, r.model_type, analysis_model),
            "chart_kinds": list(r.chart_kinds), "needs_dataset": r.needs_dataset,
            "tool": {"name": tools[r.kind].name, "description": tools[r.kind].description} if r.kind in tools else None,
            "method": _method(foundation_for_result(r.kind, r.model_type), asdict),
        }
        for r in result_surfaces()
        if model_type is None or r.model_type == model_type
    ]


def _options_schema(analysis: str, model_type: str, analysis_model) -> dict[str, Any]:
    """The JSON schema of an analysis's options, less the ones this model type's run doesn't read: the
    global-sensitivity spec is one model for seven types, and a form built from it offered a Bayesian
    network a simulation's "metric"."""
    from latris.operations.global_sensitivity import unread_options

    model = analysis_model(analysis)
    schema = model.model_json_schema()
    if model.__name__ == "GsaAnalysis":
        unread = unread_options(model_type)
        schema["properties"] = {k: v for k, v in schema.get("properties", {}).items() if k not in unread}
        # The spec's own description lists every type's options; here it is one type's.
        schema["description"] = ("Which inputs' uncertainty moves the result most: Sobol indices (each input's "
                                 "share of the spread, alone and with the others) or a cheaper Morris screen, "
                                 "over every input that has a range.")
    return schema


def _method(foundation, asdict) -> dict[str, Any] | None:
    if foundation is None:
        return None
    return {k: v for k, v in asdict(foundation).items() if k in ("id", "method", "citation", "used_for", "limits")}


def build_surface_manifest() -> dict[str, Any]:
    """Everything a surface built on this library needs to present each stable model type.

    The app's hosted report, share links and chat connector read this (or are tested against it)
    instead of keeping their own lists, so a new formalism reaches them, or fails their tests, as soon
    as they pin a release that has it. Registry-only: no project needed.

    Per type: whether it's a registered plugin, its outcome role, its build-spec block (field and JSON
    schema), its CLI group, and each result kind with its analysis (kind and JSON schema of its options),
    chart kinds and whether it needs a dataset (such results can't be re-run from a share link).
    """
    from latris import __version__
    from latris.operations import formalisms

    results: dict[str, list[dict[str, Any]]] = {}
    for entry in analysis_catalog():
        results.setdefault(entry.pop("model_type"), []).append(entry)
    types = []
    for spec in list_model_types():
        f = formalisms.get(spec.id)
        field = f.spec_field if f else _LEGACY_SPEC_FIELD.get(spec.id)
        types.append({
            "id": spec.id,
            "display_name": spec.display_name,
            "short_name": spec.short_name,
            "registered": f is not None,
            "outcome_role": f.outcome_role if f else None,
            "scope_noun": f.scope_noun if f else None,  # a quantified type that can share its map with a loop map
            "spec_field": field,
            "spec_schema": _spec_schema(field),
            "cli": f.cli[1] if f and f.cli else None,
            "chat_ops": [{"name": o.name, "fields": list(o.fields), "description": o.description, "step": o.step}
                         for o in (f.chat_ops if f else ())],
            # The value each link carries in this type, and the workflow step setting it sits in.
            "link_attribute": ({"name": f.link_attribute[0], "description": f.link_attribute[1],
                                "step": f.link_attribute_step} if f and f.link_attribute else None),
            "results": results.get(spec.id, []),
        })
    return {
        "manifest_version": SURFACE_MANIFEST_VERSION,
        "latris_version": __version__,
        "workflow": workflow_structure().model_dump(mode="json"),
        "model_types": types,
    }
