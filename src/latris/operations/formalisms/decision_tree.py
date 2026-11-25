"""Decision tree as a formalism plugin — the best choice under uncertainty (``operations/decision_tree.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    ChatOp,
    ChatTool,
    Formalism,
    ResultKind,
    _psa,
    default_origin,
    register,
    spec_verification,
)


def _threshold_lines(p: dict[str, Any]) -> list[str]:
    out = []
    for x in p["thresholds"]:
        moves = []
        if x["down"]:
            moves.append(f"falls below {x['down']['p']:.3g} ({x['down']['option']} best)")
        if x["up"]:
            moves.append(f"rises above {x['up']['p']:.3g} ({x['up']['option']} best)")
        out.append(f"P({x['uncertainty']} = {x['state']}) = {x['p']:.3g}: the best choice changes if it "
                   + (" or ".join(moves) if moves else "— never, anywhere from 0 to 1"))
    return out


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.decision_tree import describe, fmt

    u = p["units"]
    out = [describe(p) + ".", ""]
    if p.get("options"):
        out += md.table([f"{p['root']} — option", f"Expected value ({p['objective']})", ""],
                      [[o["option"], fmt(o["ev"], u), "best" if o["best"] else ""] for o in p["options"]])
    if len(p["strategy"]) > 1:
        out += ["Optimal strategy: " + "; then ".join(f"at {s['decision']}, {s['choose']}" for s in p["strategy"])
                + ".", ""]
    ev = p["evpi"]
    if ev["per_uncertainty"]:
        rows = [[x["uncertainty"], ", ".join(f"{s} {q:.3g}" for s, q in x["states"].items()),
                 fmt(x["evpi"], u), "; ".join(f"{s}: {d['choice']}" for s, d in x["by_state"].items())]
                for x in sorted(ev["per_uncertainty"], key=lambda x: -x["evpi"])]
        out += ["Expected value of perfect information — the most it is worth paying to know each uncertainty "
                "before choosing:", ""]
        out += md.table(["Uncertainty", "States", "EVPI", "Best choice if known"], rows)
        if ev["all"]:
            out += [f"Knowing everything before choosing would be worth up to {fmt(ev['all']['evpi'], u)} "
                    "(treating the uncertainties as independent).", ""]
        out += [f"Not priced: {s}." for s in ev["skipped"]]
    if p["thresholds"]:
        out += [""] + [f"- {line}" for line in _threshold_lines(p)] + [""]
    if p["unverified_on_path"]:
        out += [f"Values on the optimal path nobody has verified: {', '.join(p['unverified_on_path'])}.", ""]
    return out


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("dt-ev", {})] if p.get("options") else []


def _claims(paths, section: str) -> list[str]:
    from latris.operations import decision_tree as dt

    p = dt.analyse(root=paths.root)
    if p["problems"]:
        return [f"The decision tree is incomplete: {len(p['problems'])} structure problem(s) (e.g. "
                f"{p['problems'][0]['label']}: {p['problems'][0]['message']})"] if section == "structure" else []
    u = p["units"]
    claims: list[str] = []
    if section == "structure":
        claims.append(f"A decision tree from {p['root']}, choosing to {p['objective']} expected value"
                      + (f" in {u}" if u else "") + ".")
    elif section == "answer":
        claims.append(dt.describe(p) + ".")
        if p.get("options"):
            claims.append("Expected values: " + "; ".join(f"{o['option']} {dt.fmt(o['ev'], u)}"
                                                         for o in p["options"]) + ".")
    elif section == "sensitivity":
        claims += _threshold_lines(p)
        if p["unverified_on_path"]:
            claims.append(f"The best strategy rests on unverified values: {', '.join(p['unverified_on_path'])}.")
    elif section == "implications":
        for x in sorted(p["evpi"]["per_uncertainty"], key=lambda x: -x["evpi"]):
            if x["evpi"] > 0:
                claims.append(f"Finding out {x['uncertainty']} before choosing is worth up to {dt.fmt(x['evpi'], u)}; "
                              "research costing more than that isn't worth it.")
        if not claims and p["evpi"]["per_uncertainty"]:
            claims.append("No information about the uncertainties would change the choice; decide now.")
    elif section == "gaps":
        claims += [f"Not priced: {s}." for s in p["evpi"]["skipped"]]
    return claims


def _mermaid(paths, entities, edges) -> str:
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations import decision_tree as dt

    p = dt.analyse(root=paths.root)
    if p["problems"]:
        return ""
    lines = ["flowchart LR"]
    chosen: list[int] = []
    counter = [0]

    def walk(d: dict[str, Any]) -> str:
        nid = f"n{counter[0]}"
        counter[0] += 1
        text = _mermaid_text(d["node"])
        if d["type"] == "decision":
            lines.append(f'    {nid}["{text}<br/>EV {d["ev"]:,.4g}"]')
        elif d["type"] == "chance":
            lines.append(f'    {nid}(("{text}<br/>EV {d["ev"]:,.4g}"))')
        else:
            lines.append(f'    {nid}>"{text}<br/>{d["payoff"]:,.4g}"]')
        for b in d.get("branches", []):
            child = walk(b["to"])
            label = _mermaid_text(b["label"]) + (f" {b['probability']:.3g}" if b["probability"] is not None else "")
            if b["chosen"]:
                chosen.append(sum(1 for ln in lines if " --> " in ln))
            lines.append(f'    {nid} -->|"{label}"| {child}')
        return nid

    walk(p["tree"])
    if chosen:
        lines.append(f"    linkStyle {','.join(map(str, chosen))} stroke-width:3px")
    return "\n".join(lines) + "\n"


def _problems(root: Path) -> list:
    from latris.operations import decision_tree as dt

    return dt.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    from latris.operations.build import split_link

    problems = [f"dt node: no factor named {x.node!r}" for x in block.elements if not known(x.node)]
    problems += [f"dt payoff: no factor named {x.node!r}" for x in block.payoffs if not known(x.node)]
    problems += [f"dt uncertainty: no factor named {x.node!r}" for x in block.uncertainties if not known(x.node)]
    for b in block.branches:
        ends = split_link(b.link)
        if ends is None:
            problems.append(f"dt branch {b.link!r}: write it as 'Parent -> Child'")
        else:
            problems += [f"dt branch: no factor named {n!r}" for n in ends if not known(n)]
    return (problems + _psa.spec_check("dt", block.ranges, known)
            + _psa.spec_check_correlations("dt", block.correlations, known))


def _apply(block, verified_by: str, root: Path) -> int:
    from latris.operations import decision_tree as dt

    n = 0
    if block.objective or block.units:
        dt.set_settings(objective=block.objective, units=block.units, root=root)
        n += 1
    for x in block.elements:
        dt.set_element(x.node, x.type, root=root)
        n += 1
    for x in block.uncertainties:
        dt.set_uncertainty(x.node, x.name, root=root)
        n += 1
    for b in block.branches:
        fields = {k: v for k, v in (("label", b.label), ("probability", b.probability), ("value", b.value),
                                    ("notes", b.notes)) if v is not None}
        dt.set_branch(b.link, **fields, origin=b.origin or default_origin(verified_by), source_id=b.source,
                      verification=spec_verification(b.verified, verified_by), root=root)
        n += 1
    for x in block.payoffs:
        dt.set_payoff(x.node, x.value, origin=x.origin or default_origin(verified_by), source_id=x.source,
                      verification=spec_verification(x.verified, verified_by), notes=x.notes, root=root)
        n += 1
    n += _psa.spec_apply("decision_tree", block.ranges, verified_by, root)
    return n + _psa.spec_apply_correlations("decision_tree", block.correlations, verified_by, root)


def _export(paths, labels: dict[str, str]):
    from latris.operations import decision_tree as dt
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.build_spec import SpecDT, SpecDTBranch, SpecDTNode, SpecDTPayoff, SpecDTUncertainty

    nodes = sorted((SpecDTNode(node=labels[k], type=v) for k, v in dt.get_elements(root=paths.root).items()
                    if k in labels), key=lambda x: (x.type, x.node))
    if not nodes:
        return None
    sub = load_model(Substrate, paths.conceptual_yaml)
    ends = {e.id: (e.from_id, e.to_id) for e in sub.edges}
    branches = [SpecDTBranch(link=f"{labels[ends[b.target_id][0]]} -> {labels[ends[b.target_id][1]]}", label=b.label,
                             probability=b.probability, value=b.value, notes=b.notes, source=b.source_id,
                             origin=b.origin, verified=b.verification == "human-verified")
                for b in dt.get_branches(root=paths.root).entries
                if b.target_id in ends and all(x in labels for x in ends[b.target_id])]
    payoffs = [SpecDTPayoff(node=labels[x.target_id], value=x.value, notes=x.notes, source=x.source_id,
                            origin=x.origin, verified=x.verification == "human-verified")
               for x in dt.get_payoffs(root=paths.root).entries if x.target_id in labels]
    unc = [SpecDTUncertainty(node=labels[x.target_id], name=x.uncertainty)
           for x in dt.get_chances(root=paths.root).entries if x.target_id in labels]
    s = dt.get_settings(root=paths.root)
    return SpecDT(objective=s.objective, units=s.units, elements=nodes, branches=branches, payoffs=payoffs,
                  uncertainties=unc, ranges=_psa.spec_export("decision_tree", paths, labels),
                  correlations=_psa.spec_export_correlations("decision_tree", paths, labels))


def _run(a, root: Path) -> str:
    from latris.operations import decision_tree as dt

    payload = dt.analyse(root=root)
    if payload["problems"]:
        raise ValueError(dt.describe(payload))
    return dt.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="dt_analyse")



# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    'dt-analysis': ('analyse_decision_tree',
        'Roll back the decision tree: the best strategy by expected value, what perfect information on '
        'each uncertainty is worth (EVPI), and the probabilities at which the best choice changes. '
        'Recorded with a chart.'),
}


# How a chat assistant writes this type's build-spec block (latris-app generates each operation).
_CHAT_OPS = (
    ChatOp('set_dt_settings', ('objective', 'units'),
        'Whether the tree maximises or minimises, and the units of its payoffs.'),
    ChatOp('set_dt_element', ('elements',),
        'Make a factor a decision, chance or terminal node.'),
    ChatOp('set_dt_branch', ('branches',),
        "A branch from a node to its child ('Parent -> Child'): its label, and its probability under "
        'a chance node or value.'),
    ChatOp('set_dt_payoff', ('payoffs',),
        "A terminal node's payoff."),
    ChatOp('set_dt_uncertainty', ('uncertainties',),
        'Name the uncertainty a chance node resolves; chance nodes with the same name are the same '
        'uncertainty under different choices (for the value of information).'),
    ChatOp('set_dt_correlation', ('correlations',),
        'Two ranged values that move together (two estimates from one study): rank correlation rho, '
        '-0.99 to 0.99. The probabilistic sensitivity analysis samples them together.'),
    ChatOp('set_dt_range', ('ranges',),
        "How uncertain an input is, for probabilistic sensitivity analysis: a terminal node's payoff, a "
        "branch's value or probability ('Parent -> Child'), or a chance node's branch probabilities as a "
        'Dirichlet worth n observations. Beta and gamma take a mean and sd.'),
)

register(Formalism(
    model_type="decision_tree",
    predictor="latris.operations.predictors.decision_tree",
    outcome_role=None,
    outcome_refusal=("A decision tree's result is the best choice and its expected value, not one outcome factor: "
                     "give factors the type 'decision', 'chance' or 'terminal' (latris dt element <factor> decision)."),
    outcome_ids=lambda paths: set(),
    structure_problems=_problems,
    validators={
        "dt_structure": ("dt_no_root", "dt_many_roots", "dt_not_tree", "dt_cycle", "dt_no_decision"),
        "dt_nodes_complete": ("dt_dead_end", "dt_terminal_has_children", "dt_no_payoff"),
        "dt_probabilities_complete": ("dt_no_probability", "dt_probabilities_sum"),
    },
    whole_label="(tree)",
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Complete the probabilities and payoffs to see what would change the choice.",
    results=(ResultKind(tool=ChatTool(*_TOOLS['dt-analysis']),
                        kind="dt-analysis", title="Decision tree: best choice and the value of information",
                        render=_render, analysis="dt_analyse", run=_run, definition=_definition, charts=_charts,
                        chart_kinds=("dt-ev",)),
             _psa.result_kind('decision_tree')),
    spec_field="decision_tree",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    chat_ops=_CHAT_OPS,
    mermaid=_mermaid,
    cli=("latris.cli.dt_cmd", "dt"),
    routes="latris.server.routes.dt",
))
