"""The "Results" report section — recorded simulations, uncertainty runs, loop dominance, BN queries.

Reads :func:`latris.operations.analysis_results.report_results` (the latest
run of each analysis, minus hidden ones) and writes compact Markdown tables:
what a reader needs to see the numbers behind the answer. Results computed
before a later model change are marked out of date — or, for a reader
(``current_only``), left out, with one line saying how many there were.

With ``chart_markers=True`` (the hosted report and Word export pass it) each
result is preceded by a fenced ``latris-chart`` block naming the run and the
chart to draw; the app swaps those for SVG charts. Plain ``export md`` leaves
them out, so the Markdown stays clean.
"""

from __future__ import annotations

import json
from typing import Any

from latris.exporters import md
from latris.operations.carried_results import carried_note
from latris.repo.layout import ProjectPaths

_HUMAN_VERIFIED = "human-verified"
# Where a reader is told the results they aren't shown live. The hosted report swaps this sentence for
# one that points into the app, so keep it a sentence of its own.
HISTORY_NOTE = "They're kept in the project's analysis history."
_MAX_ROWS, _esc, _f, _table, _grounding = md.MAX_ROWS, md.esc, md.fmt, md.table, md.grounding


def _marker(run_id: str, chart: str, **extra: Any) -> list[str]:
    return ["```latris-chart", json.dumps({"run": run_id, "chart": chart, **extra}), "```", ""]


def _run_date(run_id: str) -> str:
    from latris.schema.ids import id_timestamp

    try:
        return id_timestamp(run_id).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return "date unknown"


def _stale_note(stale: bool, run_id: str, show_ids: bool) -> list[str]:
    if not stale:
        return []
    how = f" Re-run it, or hide it with `latris results hide {run_id}`." if show_ids else ""
    return [f"> **Out of date** — the model changed after this was computed.{how}", ""]


# ── per kind ─────────────────────────────────────────────────────────


def _heading(kind: str, title: str, p: dict[str, Any], plugin_kind: Any) -> str:
    world = p.get("world") if isinstance(p, dict) else None
    title = f"{title} (in every run: {'; '.join(world)})" if world else title
    try:
        sub = plugin_kind.subtitle(p) if plugin_kind is not None and plugin_kind.subtitle else ""
    except (KeyError, TypeError, ValueError, IndexError):
        sub = ""
    return f"{title}: {sub}" if sub else title


def result_charts(kind: str, payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The ``latris-chart`` markers for one result: its result kind's ``charts`` hook. Public: a surface
    drawing one result's charts (the app's results panel) draws the same ones the report marks."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    return found[1].charts(payload) if found and found[1].charts else []


def render_results(
    paths: ProjectPaths,
    *,
    model_types: list[str] | None = None,
    chart_markers: bool = False,
    show_ids: bool = True,
    current_only: bool = False,
) -> list[str]:
    """The Results section's lines, or ``[]`` when nothing has been recorded.

    ``current_only`` (reader packs): results computed on an earlier version of the model are left out, and
    so is a repeat of a result already shown (the same question asked again); one line says how many
    earlier results there are.
    """
    from latris.operations.analysis_results import report_results

    results = report_results(model_types=model_types, root=paths.root)
    if not results:
        return []
    earlier = 0
    if current_only:
        shown, seen = [], set()
        for res in results:  # newest first within each kind
            if res.stale:
                earlier += 1
                continue
            key = (res.run.result_kind, result_heading(res.run.result_kind, res.payload))
            if key not in seen:
                seen.add(key)
                shown.append(res)
        results = shown
    out = ["## Results", ""]
    if not results:
        return out + [
            "_These results were computed on an earlier version of the model and haven't been re-run "
            f"yet. {HISTORY_NOTE}_",
            "",
        ]
    out += [
        "The latest run of each analysis on this model, by the kind of analysis. Every value a run changed or "
        "sampled is listed with where it came from.",
        "",
    ]
    step = None
    for res in results:
        this = _step_of(res.run.result_kind)
        if this != step:
            step = this
            out += [f"### {_step_name(step)}", ""]
        out += render_result(res.run, res.payload, stale=res.stale, chart_markers=chart_markers,
                             show_ids=show_ids, level=4)
    if earlier:
        were = "results from earlier versions of this model aren't" if earlier != 1 else (
            "result from an earlier version of this model isn't")
        out += [f"_{earlier} {were} shown. {HISTORY_NOTE}_", ""]
    return out


def _step_of(kind: str) -> str | None:
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    return found[1].step if found else None


def _step_name(step: str | None) -> str:
    """The heading of a group of results: the workflow step's name (``schema/workflow.py``)."""
    from latris.schema.workflow import step as workflow_step

    return workflow_step(step).name if step else "Other results"


def result_heading(kind: str, p: dict[str, Any]) -> str:
    """The heading a report gives one recorded result (its title, and what it was of): public, so a surface
    that lists results (the app's results panel) names them as the report does."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    plugin_kind = found[1] if found else None
    title = kind
    if plugin_kind:
        title = plugin_kind.title_for(p) if plugin_kind.title_for else plugin_kind.title
    return _heading(kind, title, p, plugin_kind)


def render_result(run: Any, p: dict[str, Any], *, stale: bool = False, chart_markers: bool = False,
                  show_ids: bool = True, level: int = 3) -> list[str]:
    """One result's section of the report: heading (at ``level``; the report nests results under their
    workflow step, so it passes 4), date, notes, chart markers and its table."""
    kind = run.result_kind
    out = [f"{'#' * level} {result_heading(kind, p)}", "", f"_Run {_run_date(run.id)}._", ""]
    out += _stale_note(stale, run.id, show_ids)
    out += carried_note(run.hyperparameters)
    if chart_markers:
        for chart, extra in result_charts(kind, p):
            out += _marker(run.id, chart, **extra)
    try:
        out += result_body(kind, p)
    except (KeyError, TypeError, ValueError, IndexError):
        out += [f"_This result couldn't be shown ({run.output_summary})._", ""]
    return out


def result_body(kind: str, p: dict[str, Any]) -> list[str]:
    """One result's tables and notes as the report renders them (no heading, date or chart markers)."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    return found[1].render(p) if found else []
