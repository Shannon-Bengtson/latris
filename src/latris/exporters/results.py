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

from latris.repo.layout import ProjectPaths

_HUMAN_VERIFIED = "human-verified"
_MAX_ROWS = 8


def _f(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float | int):
        return f"{x:.4g}"
    return str(x)


def _esc(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_esc(c) for c in row) + " |" for row in rows]
    out.append("")
    return out


def _grounding(origin: str | None, verification: str | None) -> str:
    if verification == _HUMAN_VERIFIED:
        return "reviewed"
    who = {"ai-proposed": "AI-proposed", "data-derived": "from data", "human-elicited": "elicited"}.get(
        origin or "", "entered"
    )
    return f"{who}, not yet reviewed"


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
# Every result kind — SD's included — renders through its registry entry (``ResultKind.render``);
# see ``operations/formalisms/``.


def _heading(kind: str, title: str, p: dict[str, Any], plugin_kind: Any) -> str:
    world = p.get("world") if isinstance(p, dict) else None
    title = f"{title} (in every run: {'; '.join(world)})" if world else title
    try:
        sub = plugin_kind.subtitle(p) if plugin_kind is not None and plugin_kind.subtitle else ""
    except (KeyError, TypeError, ValueError, IndexError):
        sub = ""
    return f"{title}: {sub}" if sub else title


def result_heading(kind: str, payload: dict[str, Any]) -> str:
    """A recorded result's heading as reports show it ("Simulation: baseline vs Tax")."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    plugin_kind = found[1] if found else None
    if plugin_kind is None:
        return kind
    try:
        title = plugin_kind.title_for(payload) if plugin_kind.title_for else plugin_kind.title
    except (KeyError, TypeError, ValueError, IndexError):
        title = plugin_kind.title
    return _heading(kind, title, payload, plugin_kind)


def chart_markers(kind: str, payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The charts to draw for one result, as ``(chart kind, extra keys)`` — its registry entry's ``charts``
    hook. The app draws them (``latris_present.charts.draw``) in reports and in the editor's results panel."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    if found and found[1].charts:
        return found[1].charts(payload)
    return []


def result_body(kind: str, payload: dict[str, Any]) -> list[str]:
    """A recorded result's Markdown body (its tables); raises if the payload can't be read."""
    from latris.operations import formalisms

    found = formalisms.result_kind(kind)
    return found[1].render(payload) if found else []


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
        kind, p = res.run.result_kind, res.payload
        out.append(f"### {result_heading(kind, p)}")
        out.append("")
        out += [f"_Run {_run_date(res.run.id)}._", ""]
        out += _stale_note(res.stale, res.run.id, show_ids)
        if chart_markers:
            for chart, extra in globals()["chart_markers"](kind, p):
                out += _marker(res.run.id, chart, **extra)
        try:
            out += result_body(kind, p)
        except (KeyError, TypeError, ValueError, IndexError):
            out += [f"_This result couldn't be shown ({res.run.output_summary})._", ""]
    return out
