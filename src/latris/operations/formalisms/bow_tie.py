"""Bow-tie as a formalism plugin — threats, barriers and consequences (``operations/bow_tie.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    Formalism,
    ResultKind,
    register,
)


def _claims(paths, section: str) -> list[str]:
    """Bow-tie claims for one section, from the live analysis."""
    from latris.operations import bow_tie

    p = bow_tie.analyse(root=paths.root)
    if p["problems"]:
        if section == "structure":
            return [f"The bow-tie is incomplete: {len(p['problems'])} structure problem(s) "
                    f"(e.g. {p['problems'][0]['label']}: {p['problems'][0]['message']})"]
        return []
    f = bow_tie.flags(p)
    claims: list[str] = []
    if section == "structure":
        claims.append(bow_tie.describe(p) + ".")
        if p["hazard"]:
            claims.append(f"Hazard: {p['hazard']}; top event: {p['top']}.")
        if p["outside_inputs"]:
            claims.append(f"Left out of the bow-tie (no bow-tie role): {', '.join(p['outside_inputs'][:5])}.")
    elif section == "answer":
        if f["unprotected"]:
            claims.append(f"Lines with no effective barrier: {', '.join(f['unprotected'])}.")
        if f["single_barrier"]:
            claims.append(f"Lines resting on a single effective barrier: {', '.join(f['single_barrier'])}.")
        if not f["unprotected"] and not f["single_barrier"]:
            claims.append("Every line has at least two effective barriers.")
        if p["quantified"]:
            fr = p["frequency"]
            claims.append(f"Estimated frequency of {p['top']}: {fr['top']:.3g} per year (layer of protection; "
                          "barriers assumed independent).")
            claims.append("Consequences per year: " + "; ".join(f"{c} {v:.3g}" for c, v in fr["consequences"].items())
                          + ".")
    elif section == "sensitivity" and p["quantified"]:
        ranked = [b for b in p["barriers"] if b["raw"] is not None][:5]
        claims.append("Barriers by how much they buy (RAW: how many times more often their side's outcome would "
                      "happen if the barrier always failed):")
        claims += [f"  - {b['barrier']} ({b['side']}): {b['raw']:.3g}" + (" (value not verified)" if b["weak"] else "")
                   for b in ranked]
        weak = [b["barrier"] for b in ranked[:3] if b["weak"]]
        if weak:
            claims.append(f"The barriers that matter most whose failure probability nobody has verified: "
                          f"{', '.join(weak)}.")
    elif section == "implications":
        if f["unprotected"] or f["single_barrier"]:
            claims.append("Where another independent barrier would help most: "
                          + ", ".join(f["unprotected"] + f["single_barrier"]) + ".")
        if f["shared"]:
            claims.append(f"Barriers on more than one line — one failure defeats every line they guard: "
                          f"{', '.join(f['shared'])}.")
        if f["uncontrolled_escalation"]:
            claims.append(f"Escalation factors with no control: {', '.join(f['uncontrolled_escalation'])}.")
        if f["not_in_place"]:
            claims.append(f"Barriers degraded or not in place: {', '.join(f['not_in_place'])}.")
        if f["no_owner"]:
            claims.append(f"Barriers nobody owns: {', '.join(f['no_owner'])}.")
    elif section == "gaps":
        if p["missing"]:
            claims.append(f"Not quantified — missing: {', '.join(p['missing'][:6])}"
                          + (f" (+{len(p['missing']) - 6} more)." if len(p["missing"]) > 6 else "."))
        unsourced = [b["barrier"] for b in p["barriers"] if b["pfd"] is not None and not b["source"]]
        if unsourced:
            claims.append(f"Failure probabilities with no stated source: {', '.join(unsourced[:5])}.")
    return claims


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _MAX_ROWS, _esc, _f, _table  # noqa: F401
    from latris.operations.bow_tie import describe, flags

    out = [describe(p) + ".", ""]
    if p.get("quantified"):
        fr = p["frequency"]
        cons = "; ".join(f"{c} {_f(v)}" for c, v in fr["consequences"].items())
        out += [f"Top-event frequency: **{_f(fr['top'])} per year** (layer of protection, barriers assumed "
                f"independent); consequences per year: {cons}.", ""]
    rows = [[ln["side"], ln["from"] + " → " + ln["to"], " → ".join(ln["barriers"]) or "—", str(ln["effective"])]
            for ln in sorted(p["lines"], key=lambda ln: (ln["effective"], ln["side"]))[: _MAX_ROWS * 2]]
    if rows:
        out += _table(["Side", "Line", "Barriers", "Effective"], rows)
    f = flags(p)
    notes = [(f["unprotected"], "No effective barrier"), (f["single_barrier"], "Resting on one barrier"),
             (f["shared"], "Barriers on more than one line (one failure takes them all)"),
             (f["uncontrolled_escalation"], "Escalation factors with no control"),
             (f["not_in_place"], "Barriers degraded or not in place"), (f["no_owner"], "Barriers with no owner")]
    out += [f"- **{title}:** {', '.join(items)}" for items, title in notes if items]
    if any(items for items, _ in notes):
        out.append("")
    if p.get("quantified"):
        rows = [[b["barrier"], b["side"], _f(b["pfd"]), _f(b["raw"]),
                 (b["origin"] or "—") + (f" ({b['source']})" if b["source"] else "")
                 + ("; not verified" if b["weak"] else "")]
                for b in p["barriers"] if b["side"] != "escalation control"][:_MAX_ROWS]
        out += ["*RAW*: how many times more often the top event (prevention) or its consequences (mitigation) "
                "would happen if the barrier always failed.", ""]
        out += _table(["Barrier", "Side", "Failure probability", "RAW", "Where it came from"], rows)
    return out


def _mermaid(paths, entities, edges) -> str:
    """Threats on the left, the top event in the middle, consequences on the right; barriers as boxes."""
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations.bow_tie import EDGE_KINDS, get_barriers, get_elements

    el = get_elements(root=paths.root)
    members = [e for e in entities if e.id in el]
    if not members:
        return ""
    barriers = {b.target_id: b for b in get_barriers(root=paths.root).entries}
    alias = {e.id: f"n{i}" for i, e in enumerate(members)}
    shapes = {"hazard": ('[/"', '"/]'), "top_event": ('(("', '"))'), "threat": ('(["', '"])'),
              "consequence": ('(["', '"])'), "barrier": ('["', '"]'), "escalation_factor": ('>"', '"]')}
    lines = ["flowchart LR"]
    for e in members:
        text = _mermaid_text(e.label)
        b = barriers.get(e.id)
        if b and b.status != "in_place":
            text += f"<br/>{b.status.replace('_', ' ')}"
        if b and b.pfd is not None:
            text += f"<br/>pfd {b.pfd:g}"
        a, z = shapes[el[e.id]]
        lines.append(f"    {alias[e.id]}{a}{text}{z}")
    for ed in edges:
        if ed.kind in EDGE_KINDS and ed.from_id in alias and ed.to_id in alias:
            arrow = "-.->" if el[ed.from_id] in ("escalation_factor", "hazard") else "-->"
            lines.append(f"    {alias[ed.from_id]} {arrow} {alias[ed.to_id]}")
    weak = [alias[e.id] for e in members if (b := barriers.get(e.id)) and b.status != "in_place"]
    if weak:
        lines.append(f"    style {','.join(weak)} stroke:#c0392b,stroke-dasharray:4 3")
    return "\n".join(lines) + "\n"


def _export(paths, labels: dict[str, str]):  # noqa: ANN001, ANN202
    """Bow-tie elements, barriers and threat frequencies as spec entries."""
    from latris.operations import bow_tie as bt
    from latris.schema.bow_tie import BT_ELEMENTS
    from latris.schema.build_spec import SpecBowTie, SpecBTBarrier, SpecBTElement, SpecBTFrequency

    elements = sorted(
        (SpecBTElement(node=labels[eid], type=t) for eid, t in bt.get_elements(root=paths.root).items()
         if eid in labels),
        key=lambda e: (BT_ELEMENTS.index(e.type), e.node),
    )
    if not elements:
        return None
    barriers = [
        SpecBTBarrier(node=labels[b.target_id], type=b.barrier_type, status=b.status, owner=b.owner, pfd=b.pfd,
                      source=b.source_id, origin=b.origin, verified=b.verification == "human-verified", notes=b.notes)
        for b in bt.get_barriers(root=paths.root).entries if b.target_id in labels
    ]
    freqs = [
        SpecBTFrequency(node=labels[f.target_id], frequency=f.frequency, source=f.source_id, origin=f.origin,
                        verified=f.verification == "human-verified", notes=f.notes)
        for f in bt.get_frequencies(root=paths.root).entries if f.target_id in labels
    ]
    return SpecBowTie(elements=elements, barriers=barriers, frequencies=freqs)


def _apply(spec_bt, verified_by: str, root: Path) -> int:
    """Elements first (barrier values and frequencies need them), then barriers, then frequencies."""
    from latris.operations import bow_tie as bt_ops

    default_origin = "ai-proposed" if verified_by == "ai" else "human-direct"

    def verification(v: bool) -> str:
        return "human-verified" if v and verified_by == "human" else "unverified"

    n = 0
    for e in spec_bt.elements:
        bt_ops.set_element(e.node, e.type, root=root)
        n += 1
    for b in spec_bt.barriers:
        bt_ops.set_barrier(
            b.node, barrier_type=b.type, status=b.status, owner=b.owner, pfd=b.pfd, notes=b.notes,
            origin=b.origin or default_origin, source_id=b.source, verification=verification(b.verified), root=root,
        )
        n += 1
    for f in spec_bt.frequencies:
        bt_ops.set_frequency(f.node, f.frequency, origin=f.origin or default_origin, source_id=f.source,
                             verification=verification(f.verified), notes=f.notes, root=root)
        n += 1
    return n


def _outcome_ids(paths) -> set[str]:
    from latris.operations import bow_tie

    return {eid for eid, t in bow_tie.get_elements(root=paths.root).items() if t == "top_event"}


def _set_outcome(target: str, root: Path) -> Any:
    from latris.operations import bow_tie

    return bow_tie.set_element(target, "top_event", root=root)


def _problems(root: Path) -> list:
    from latris.operations import bow_tie

    return bow_tie.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    problems = []
    for where, nodes in (("bowtie element", [x.node for x in block.elements]),
                         ("bowtie barrier", [x.node for x in block.barriers]),
                         ("bowtie frequency", [x.node for x in block.frequencies])):
        for n in nodes:
            if not known(n):
                problems.append(f"{where}: no factor named {n!r}")
    for e in block.elements:
        if outcome and e.node.casefold() == outcome.casefold() and e.type != "top_event":
            problems.append(f"bowtie element: {e.node!r} is the outcome, so it is the top event, not {e.type}")
    return problems


def _run(a, root: Path) -> str:
    from latris.operations import bow_tie

    payload = bow_tie.analyse(root=root)
    if payload["problems"]:
        raise ValueError(bow_tie.describe(payload))
    return bow_tie.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import SpecAnalysis

    return SpecAnalysis(kind="bowtie_analyse")


register(Formalism(
    model_type="bow_tie",
    outcome_role="top_event",
    outcome_refusal=(
        "A bow-tie's outcome of interest is its top event: give the factor the element 'top_event' "
        "(latris bowtie element <factor> top_event)."
    ),
    outcome_ids=_outcome_ids,
    set_outcome=_set_outcome,
    structure_problems=_problems,
    validators={
        "bt_elements_classified": ("bt_no_top", "bt_many_tops", "bt_many_hazards", "bt_no_threat",
                                   "bt_no_consequence"),
        "bt_links_valid": ("bt_bad_link", "bt_cycle", "bt_hazard_unlinked"),
        "bt_lines_complete": ("bt_threat_unlinked", "bt_consequence_unlinked", "bt_barrier_off_line",
                              "bt_escalation_unlinked"),
    },
    whole_label="(bow-tie)",
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback=("Give every threat a frequency and every barrier a failure probability to rank the "
                          "barriers by how much they buy."),
    results=(ResultKind(kind="bt-analysis", title="Bow-tie: lines, barriers and frequencies", render=_render,
                        analysis="bowtie_analyse", run=_run, definition=_definition),),
    spec_field="bowtie",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    mermaid=_mermaid,
    cli=("latris.cli.bowtie_cmd", "bowtie"),
    routes="latris.server.routes.bowtie",
))
