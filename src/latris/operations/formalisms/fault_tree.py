"""Fault tree as a formalism plugin — gates down to basic events (``operations/fault_tree.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    ChatOp,
    ChatTool,
    Formalism,
    ResultKind,
    _risk_mc,
    register,
)


def _claims(paths, section: str) -> list[str]:
    """Fault-tree claims for one section, from the live analysis."""
    from latris.operations import fault_tree

    p = fault_tree.analyse(root=paths.root)
    claims: list[str] = []
    if p["problems"]:
        if section == "structure":
            claims.append(f"The fault tree is incomplete: {len(p['problems'])} structure problem(s) "
                          f"(e.g. {p['problems'][0]['label']}: {p['problems'][0]['message']})")
        return claims
    if p["error"]:
        return [p["error"]] if section == "structure" else []
    imp = p["importance"]
    if section == "structure":
        c = p["counts"]
        claims.append(f"Fault tree for {p['top']}: {c['intermediate_event']} intermediate event(s), "
                      f"{c['basic_event']} basic and {c['undeveloped_event']} undeveloped event(s).")
        claims.append(fault_tree.describe(p) + ".")
        if p["outside_inputs"]:
            claims.append(f"Left out of the tree (no fault-tree type): {', '.join(p['outside_inputs'][:5])}.")
    elif section == "answer":
        if p["quantified"]:
            claims.append(f"Probability of {p['top']}: {p['probability']['exact']:.3g} (exact, assuming the basic "
                          "events are independent).")
            top = p["cut_sets"][:3]
            if top:
                claims.append("Most likely ways it happens: " + "; ".join(
                    f"{' AND '.join(c['events'])} ({c['probability']:.3g})" for c in top) + ".")
        else:
            claims.append(f"{p['top']} can happen in {p['cut_sets_total']} minimal way(s); it isn't quantified "
                          f"until every basic event has a probability.")
        if p["single_points"]:
            claims.append(f"Single points of failure — one event alone causes {p['top']}: "
                          f"{', '.join(p['single_points'])}.")
    elif section == "sensitivity" and imp:
        claims.append("Basic events by importance (Fussell–Vesely: the share of the top-event probability that "
                      "needs the event):")
        claims += [f"  - {i['event']}: {i['fussell_vesely']:.2f}" + (" (value not verified)" if i["weak"] else "")
                   for i in imp[:5]]
        weak = [i["event"] for i in imp[:3] if i["weak"]]
        if weak:
            claims.append(f"The most important values nobody has verified yet: {', '.join(weak)} — check these first.")
    elif section == "implications":
        if p["single_points"]:
            claims.append(f"Redundancy or a barrier at a single point of failure removes a whole way {p['top']} "
                          f"happens: {', '.join(p['single_points'])}.")
        if imp:
            claims.append("Largest reductions in the top-event probability if these events could not happen "
                          "(Fussell–Vesely):")
            claims += [f"  - {i['event']} ({i['fussell_vesely']:.0%} of the probability)" for i in imp[:3]]
    elif section == "gaps":
        if p["missing_probabilities"]:
            claims.append(f"Basic events without a probability: {', '.join(p['missing_probabilities'][:5])}"
                          + (f" (+{len(p['missing_probabilities']) - 5} more)." if len(p["missing_probabilities"]) > 5
                             else "."))
        unsourced = [i["event"] for i in imp if not i["source"]]
        if unsourced:
            claims.append(f"Probabilities with no stated source: {', '.join(unsourced[:5])}.")
    return claims


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("ft-importance", {})] if p.get("importance") else []


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.fault_tree import describe

    out = [describe(p) + ".", ""]
    if p.get("quantified"):
        pr = p["probability"]
        out += [f"Top-event probability: **{md.fmt(pr['exact'])}** (exact, assuming independent basic events); "
                f"rare-event approximation {md.fmt(pr['rare_event'])}, min-cut upper bound "
                f"{md.fmt(pr['min_cut_upper_bound'])}.", ""]
    if p.get("cut_sets"):
        rows = [[" AND ".join(c["events"]), str(c["order"]), md.fmt(c["probability"])]
                for c in p["cut_sets"][:md.MAX_ROWS]]
        out += md.table(["Minimal cut set", "Order", "Probability"], rows)
        if p["cut_sets_total"] > md.MAX_ROWS:
            out += [f"_…and {p['cut_sets_total'] - md.MAX_ROWS} more cut set(s)._", ""]
    if p.get("importance"):
        rows = [
            [i["event"], md.fmt(i["probability"]), f"{i['fussell_vesely']:.3f}", md.fmt(i["birnbaum"]),
             md.fmt(i["raw"]) if i["raw"] is not None else "—",
             i["origin"] + (f" ({i['source']})" if i["source"] else "") + ("; not verified" if i["weak"] else "")]
            for i in p["importance"][:md.MAX_ROWS]
        ]
        out += ["Importance, most first. *Fussell–Vesely*: the share of the top-event probability that needs the "
                "event; *Birnbaum*: how far the top-event probability moves between the event surely happening "
                "and surely not; *RAW*: how many times likelier the top event is if the event happens.", ""]
        out += md.table(["Basic event", "Probability", "Fussell–Vesely", "Birnbaum", "RAW", "Where it came from"],
                      rows)
    if p.get("outside_inputs"):
        out += ["Left out of the tree (inputs from factors that have no fault-tree type): "
                + "; ".join(p["outside_inputs"]) + ".", ""]
    return out


def _mermaid(paths, entities, edges) -> str:
    """Top event at the top; each gated event names its gate; leaves show their probability."""
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations.fault_tree import EDGE_KINDS, get_events, get_gates, get_probabilities

    events = get_events(root=paths.root)
    members = [e for e in entities if e.id in events]
    if not members:
        return ""
    gates = {g.target_id: g for g in get_gates(root=paths.root).entries}
    probs = {p.target_id: p.probability for p in get_probabilities(root=paths.root).entries}
    alias = {e.id: f"n{i}" for i, e in enumerate(members)}
    lines = ["flowchart TB"]
    for e in members:
        text = _mermaid_text(e.label)
        g = gates.get(e.id)
        if g:
            text += f"<br/>{'VOTE ' + str(g.k) if g.gate == 'vote' else g.gate.upper()}"
        if e.id in probs:
            text += f"<br/>p = {probs[e.id]:.3g}"
        shape = ('(["', '"])') if events[e.id] == "basic_event" else (
            ('{{"', '"}}') if events[e.id] == "undeveloped_event" else ('["', '"]'))
        lines.append(f"    {alias[e.id]}{shape[0]}{text}{shape[1]}")
    for ed in edges:
        if ed.kind in EDGE_KINDS and ed.from_id in alias and ed.to_id in alias:
            lines.append(f"    {alias[ed.to_id]} --- {alias[ed.from_id]}")
    return "\n".join(lines) + "\n"


def _export(paths, labels: dict[str, str]):  # noqa: ANN001, ANN202
    """Fault-tree event types, gates and probabilities as spec entries."""
    from latris.operations import fault_tree as ft
    from latris.schema.build_spec import SpecFT, SpecFTEvent, SpecFTGate, SpecFTProbability
    from latris.schema.fault_tree import FT_EVENT_TYPES

    events = sorted(
        (SpecFTEvent(node=labels[eid], type=t) for eid, t in ft.get_events(root=paths.root).items() if eid in labels),
        key=lambda e: (FT_EVENT_TYPES.index(e.type), e.node),
    )
    if not events:
        return None
    gates = [SpecFTGate(node=labels[g.target_id], gate=g.gate, k=g.k)
             for g in ft.get_gates(root=paths.root).entries if g.target_id in labels]
    probs = [
        SpecFTProbability(node=labels[p.target_id], probability=p.probability, source=p.source_id, origin=p.origin,
                          verified=p.verification == "human-verified", notes=p.notes)
        for p in ft.get_probabilities(root=paths.root).entries if p.target_id in labels
    ]
    return SpecFT(events=events, gates=gates, probabilities=probs,
                  uncertainty=_risk_mc.spec_export("fault_tree", paths, labels))


def _apply(spec_ft, verified_by: str, root: Path) -> int:
    """Event types first (gates and probabilities need them), then gates, then probabilities."""
    from latris.operations import fault_tree as ft_ops

    default_origin = "ai-proposed" if verified_by == "ai" else "human-direct"
    n = 0
    for e in spec_ft.events:
        ft_ops.set_event(e.node, e.type, root=root)
        n += 1
    for g in spec_ft.gates:
        ft_ops.set_gate(g.node, g.gate, k=g.k, root=root)
        n += 1
    for p in spec_ft.probabilities:
        ft_ops.set_probability(
            p.node, p.probability, origin=p.origin or default_origin, source_id=p.source,
            verification="human-verified" if p.verified and verified_by == "human" else "unverified",
            notes=p.notes, root=root,
        )
        n += 1
    return n + _risk_mc.spec_apply("fault_tree", spec_ft.uncertainty, verified_by, root)


def _outcome_ids(paths) -> set[str]:
    from latris.operations import fault_tree

    return {eid for eid, t in fault_tree.get_events(root=paths.root).items() if t == "top_event"}


def _set_outcome(target: str, root: Path) -> Any:
    from latris.operations import fault_tree

    return fault_tree.set_event(target, "top_event", root=root)


def _problems(root: Path) -> list:
    from latris.operations import fault_tree

    return fault_tree.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    problems = []
    for where, nodes in (("ft event", [x.node for x in block.events]),
                         ("ft gate", [x.node for x in block.gates]),
                         ("ft probability", [x.node for x in block.probabilities])):
        for n in nodes:
            if not known(n):
                problems.append(f"{where}: no factor named {n!r}")
    for g in block.gates:
        if (g.gate == "vote") != (g.k is not None):
            problems.append(f"ft gate {g.node!r}: k goes with a vote gate, and only with one")
    for e in block.events:
        if outcome and e.node.casefold() == outcome.casefold() and e.type != "top_event":
            problems.append(f"ft event: {e.node!r} is the outcome, so it is the top event, not {e.type}")
    return problems + _risk_mc.spec_check("ft", block.uncertainty, known)


def _run(a, root: Path) -> str:
    from latris.operations import fault_tree

    payload = fault_tree.analyse(max_order=a.max_order, root=root)
    if payload["problems"] or payload["error"]:
        raise ValueError(fault_tree.describe(payload))
    return fault_tree.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="ft_analyse", max_order=payload.get("max_order"))



# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    'ft-analysis': ('analyse_fault_tree',
        'Fault tree: minimal cut sets (up to max_order), single points of failure, the top-event '
        "probability and each event's importance (Fussell-Vesely, Birnbaum, RAW), flagging important "
        'values nobody has verified. Recorded with a chart.'),
}


# How a chat assistant writes this type's build-spec block (latris-app generates each operation).
_CHAT_OPS = (
    ChatOp('set_ft_event', ('events',),
        'Make a factor a top, intermediate, basic or undeveloped event (link inputs to the event they '
        "feed with kind 'logical')."),
    ChatOp('set_ft_gate', ('gates',),
        "The gate combining an event's inputs: and, or, or vote (k out of n)."),
    ChatOp('set_ft_probability', ('probabilities',),
        "A basic event's probability, with its source."),
    ChatOp('set_ft_uncertainty', ('uncertainty',),
        'An uncertainty on a probability: a distribution and its parameters, with the reason; '
        'monte_carlo_fault_tree samples it.'),
)

register(Formalism(
    model_type="fault_tree",
    predictor="latris.operations.predictors.fault_tree",
    outcome_role="top_event",
    outcome_refusal=(
        "A fault tree's outcome of interest is its top event: give the factor the type 'top_event' "
        "(latris ft event <factor> top_event)."
    ),
    outcome_ids=_outcome_ids,
    set_outcome=_set_outcome,
    structure_problems=_problems,
    validators={
        "ft_events_classified": ("ft_no_top", "ft_many_tops"),
        "ft_gates_complete": ("ft_no_gate", "ft_no_inputs", "ft_vote_k", "ft_leaf_has_inputs"),
        "ft_tree_connected": ("ft_cycle", "ft_not_in_tree"),
    },
    whole_label="(tree)",
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Give every basic event a probability to rank the events by importance.",
    results=(ResultKind(tool=ChatTool(*_TOOLS['ft-analysis']),
                        kind="ft-analysis", title="Fault tree: cut sets, probability and importance", render=_render,
                        analysis="ft_analyse", run=_run, definition=_definition, charts=_charts,
                        chart_kinds=("ft-importance",)),
             _risk_mc.result_kind("fault_tree")),
    spec_field="ft",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    chat_ops=_CHAT_OPS,
    mermaid=_mermaid,
    cli=("latris.cli.ft_cmd", "ft"),
    routes="latris.server.routes.ft",
))
