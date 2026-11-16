"""Theory of Change as a formalism plugin — results chains from activities to impact (``operations/toc.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    Formalism,
    ResultKind,
    register,
)


def _claims(paths, section: str) -> list[str]:
    """Theory-of-change claims for one section, from the live pathway analysis."""
    from latris.operations import toc

    payload, _ = toc.check(record=False, root=paths.root)
    pws, on = payload["pathways"], [lk for lk in payload["links"] if lk["on_pathway"]]
    by_status = {s: sum(1 for p in pws if p["status"] == s) for s in ("checked", "cited", "untested", "contested")}
    claims: list[str] = []
    if section == "structure":
        counts = ", ".join(f"{n} {toc.LEVEL_NAMES[lvl].lower()}" for lvl, n in payload["counts"].items() if n)
        if counts:
            claims.append(f"Results chain by level: {counts}.")
        claims.append(toc.describe(payload) + ".")
        leaps = [lk["label"] for lk in on if lk["leap"]]
        if leaps:
            claims.append(f"Links that skip levels, leaving the steps between unstated: {', '.join(leaps[:5])}.")
        if payload["problems"]:
            claims.append(
                f"The results chain is incomplete: {len(payload['problems'])} structure problem(s) "
                f"(e.g. {payload['problems'][0]['label']}: {payload['problems'][0]['message']})"
            )
    elif section == "answer":
        if not pws:
            claims.append("No pathway yet runs from an activity to an impact, so the theory doesn't say how the "
                          "intervention would reach its goal.")
        else:
            claims.append(
                f"Of {len(pws)} pathway(s) from activity to impact, {by_status['checked']} rest entirely on links "
                f"checked against a source; {by_status['cited']} have a link whose sources aren't checked yet, "
                f"{by_status['untested']} a link with no source and {by_status['contested']} a contested link."
            )
            best = [p for p in pws if p["status"] == "checked"]
            if best:
                claims.append(f"Best-supported pathway: {' → '.join(best[0]['path'])}.")
    elif section == "gaps":
        untested = [lk["label"] for lk in on if lk["status"] == "untested"]
        contested = [lk["label"] for lk in on if lk["status"] == "contested"]
        no_assumption = [lk["label"] for lk in on if not lk["assumptions"]]
        if untested:
            claims.append(f"Links on a pathway with no source: {', '.join(untested[:5])}"
                          + (f" (+{len(untested) - 5} more)." if len(untested) > 5 else "."))
        if contested:
            claims.append(f"Links on a pathway with a source against them: {', '.join(contested[:5])}.")
        if no_assumption:
            claims.append(f"{len(no_assumption)} of {len(on)} link(s) on a pathway have no stated assumption "
                          "about why the step should happen.")
    elif section == "implications":
        weak = {}
        for p in pws:
            for name in p["weak_links"]:
                weak[name] = weak.get(name, 0) + 1
        status = {lk["label"]: lk["status"] for lk in on}
        if weak:
            rank = {"contested": 0, "untested": 1, "cited": 2}
            top = sorted(weak.items(), key=lambda kv: (-kv[1], rank.get(status.get(kv[0], ""), 3), kv[0]))[:3]
            claims.append("Links to test first — not yet checked, and on the most pathways:")
            claims += [f"  - {name} ({status.get(name, '?')}; on {n} pathway(s))" for name, n in top]
        elif pws:
            claims.append("Every link on a pathway has been checked against a source.")
    return claims


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _MAX_ROWS, _esc, _f, _table  # noqa: F401
    from latris.operations.toc import describe

    out = [describe(p) + ".", ""]
    if p.get("problems"):
        out += [f"The results chain is incomplete ({len(p['problems'])} structure problem(s)):", ""]
        out += [f"- {_esc(x['label'])}: {_esc(x['message'])}" for x in p["problems"][:_MAX_ROWS]]
        out.append("")
    order = {"contested": 0, "untested": 1, "cited": 2, "checked": 3}
    pws = sorted(p["pathways"], key=lambda x: order.get(x["status"], 9))
    if pws:
        rows = [[" → ".join(x["path"]), x["status"], ", ".join(x["weak_links"]) or "—"]
                for x in pws[:_MAX_ROWS]]
        out += _table(["Pathway", "Weakest link", "Links not yet checked"], rows)
        if len(pws) > _MAX_ROWS:
            out += [f"_…and {len(pws) - _MAX_ROWS} more pathway(s)._", ""]
    on = [lk for lk in p["links"] if lk["on_pathway"]]
    if on:
        rows = [
            [lk["label"], lk["status"], str(lk["sources_for"]), str(lk["sources_for_checked"]),
             str(lk["sources_against"]), str(lk["assumptions"]), "skips levels" if lk["leap"] else ""]
            for lk in sorted(on, key=lambda lk: order.get(lk["status"], 9))[: _MAX_ROWS * 2]
        ]
        out += ["Each link on a pathway, weakest first. *Checked*: a source was read and found to support it; "
                "*cited*: it has a source not yet checked; *untested*: no source; *contested*: a source argues "
                "against it.", ""]
        out += _table(["Link", "Evidence", "Sources for", "Checked", "Against", "Assumptions", "Note"], rows)
    return out


def _export(paths, labels: dict[str, str]):  # noqa: ANN001, ANN202
    """Theory-of-change levels as spec entries, inputs first."""
    from latris.operations import toc
    from latris.schema.build_spec import SpecToC, SpecToCLevel

    levels = toc.get_levels(root=paths.root)
    entries = sorted(
        (SpecToCLevel(node=labels[eid], level=lvl) for eid, lvl in levels.items() if eid in labels),
        key=lambda e: (toc.LEVELS.index(e.level), e.node),
    )
    return SpecToC(levels=entries) if entries else None


def _groups(paths) -> tuple[list[str], dict[str, str], dict[str, str]]:
    from latris.operations.toc import LEVEL_NAMES, LEVELS, get_levels

    return list(LEVELS), dict(LEVEL_NAMES), get_levels(root=paths.root)


def _outcome_ids(paths) -> set[str]:
    from latris.operations import toc

    return {eid for eid, lvl in toc.get_levels(root=paths.root).items() if lvl == "impact"}


def _set_outcome(target: str, root: Path) -> Any:
    from latris.operations import toc

    return toc.set_level(target, "impact", root=root)


def _problems(root: Path) -> list:
    from latris.operations import toc

    return toc.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    problems = []
    for lv in block.levels:
        if not known(lv.node):
            problems.append(f"toc level: no factor named {lv.node!r}")
        if outcome and lv.node.casefold() == outcome.casefold() and lv.level != "impact":
            problems.append(f"toc level: {lv.node!r} is the outcome, so its level is impact, not {lv.level}")
    return problems


def _apply(block, verified_by: str, root: Path) -> int:
    from latris.operations import toc

    for lv in block.levels:
        toc.set_level(lv.node, lv.level, root=root)
    return len(block.levels)


def _run(a, root: Path) -> str:
    from latris.operations import toc

    return toc.check(root=root)[0]["run_id"]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import SpecAnalysis

    return SpecAnalysis(kind="toc_check")


def _fingerprint(paths) -> list[Path]:
    # The pathway check reads each link's sources, checks, assumptions and confidence.
    return [paths.evidence_links_yaml, paths.assumptions_yaml, paths.confidence_yaml]


register(Formalism(
    model_type="theory_of_change",
    outcome_role="impact",
    outcome_refusal=(
        "A theory of change's outcome of interest is its impact: give the factor the level 'impact' "
        "(latris toc level <factor> impact). Outcomes along the way are short_term_outcome or long_term_outcome."
    ),
    outcome_ids=_outcome_ids,
    set_outcome=_set_outcome,
    structure_problems=_problems,
    validators={
        "toc_levels_complete": ("toc_no_level",),
        "toc_links_forward": ("toc_backward_link",),
        "toc_pathways_complete": ("toc_no_activity", "toc_no_impact", "toc_dead_end", "toc_unreached_impact"),
    },
    claims=_claims,
    centrality=True,
    own_implications=True,
    results=(ResultKind(kind="toc-pathways", title="Theory of change: pathways and their evidence", render=_render,
                        analysis="toc_check", run=_run, definition=_definition),),
    fingerprint_files=_fingerprint,
    spec_field="toc",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    mermaid_groups=_groups,
    cli=("latris.cli.toc_cmd", "toc"),
    routes="latris.server.routes.toc",
))
