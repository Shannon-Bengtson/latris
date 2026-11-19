"""The "Results" report section — recorded simulations, uncertainty runs, loop dominance, BN queries.

Reads :func:`latris.operations.analysis_results.report_results` (the latest
run of each analysis, minus hidden ones) and writes compact Markdown tables:
what a reader needs to see the numbers behind the answer. Results computed
before a later model change are marked out of date.

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


def _charts(kind: str, payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The ``latris-chart`` markers for one result: its result kind's ``charts`` hook."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    return found[1].charts(payload) if found and found[1].charts else []


def render_results(
    paths: ProjectPaths,
    *,
    model_types: list[str] | None = None,
    chart_markers: bool = False,
    show_ids: bool = True,
) -> list[str]:
    """The Results section's lines, or ``[]`` when nothing has been recorded."""
    from latris.operations.analysis_results import report_results

    results = report_results(model_types=model_types, root=paths.root)
    if not results:
        return []
    out = [
        "## Results",
        "",
        "The latest run of each analysis on this model. Every value a run changed or sampled is listed "
        "with where it came from.",
        "",
    ]
    for res in results:
        out += render_result(res.run, res.payload, stale=res.stale, chart_markers=chart_markers, show_ids=show_ids)
    return out


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
                  show_ids: bool = True) -> list[str]:
    """One result's section of the report: heading, date, notes, chart markers and its table."""
    from latris.operations import formalisms

    kind = run.result_kind
    found = formalisms.result_kind(kind)
    plugin_kind = found[1] if found else None
    out = [f"### {result_heading(kind, p)}", "", f"_Run {_run_date(run.id)}._", ""]
    out += _stale_note(stale, run.id, show_ids)
    out += carried_note(run.hyperparameters)
    if chart_markers:
        for chart, extra in _charts(kind, p):
            out += _marker(run.id, chart, **extra)
    try:
        if plugin_kind:
            out += plugin_kind.render(p)
    except (KeyError, TypeError, ValueError, IndexError):
        out += [f"_This result couldn't be shown ({run.output_summary})._", ""]
    return out
