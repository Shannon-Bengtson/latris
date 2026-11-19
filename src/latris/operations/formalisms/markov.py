"""Markov cohort model as a formalism plugin — costs and outcomes over time (``operations/markov.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import (
    ChatOp,
    ChatTool,
    Formalism,
    ResultKind,
    default_origin,
    register,
    spec_verification,
)


def _units(p: dict[str, Any]) -> tuple[str | None, str]:
    s = p["settings"]
    return s["cost_units"], s["outcome_units"] or "outcome units"


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.markov import _money, describe

    cu, ou = _units(p)
    s = p["settings"]
    out = [describe(p) + ".", ""]
    out += [f"{s['num_cycles']} cycles of {s['cycle_length']:g} {s['time_units']}; discounting "
            f"{s['discount_rate']:.1%} for costs, "
            f"{(s['outcome_discount_rate'] if s['outcome_discount_rate'] is not None else s['discount_rate']):.1%} "
            f"for outcomes; half-cycle correction {'on' if s['half_cycle_correction'] else 'off'}.", ""]
    rows = [[r["strategy"], _money(r["cost"], cu), f"{r['outcome']:.3f}", _money(r["cost_undiscounted"], cu),
             f"{r['outcome_undiscounted']:.3f}"] for r in p["results"]]
    out += md.table(["Strategy", "Cost (discounted)", f"{ou} (discounted)", "Cost (undiscounted)",
                   f"{ou} (undiscounted)"], rows)
    if p.get("incremental"):
        rows = [[r["strategy"], _money(r["cost"], cu), f"{r['outcome']:.3f}", r["status"],
                 (_money(r["icer"], cu) + f" per {ou} vs {r['versus']}") if r["icer"] is not None
                 else (f"by {r['versus']}" if r["status"] == "dominated" else "—")] for r in p["incremental"]]
        out += ["Incremental analysis, cheapest first. A strategy is *dominated* when another costs no more and "
                "achieves at least as much; *extendedly dominated* when a mix of its neighbours would beat it.", ""]
        out += md.table(["Strategy", "Cost", ou, "Status", "ICER"], rows)
        if p.get("choice"):
            out += [f"At a willingness to pay of {_money(s['wtp'], cu)} per {ou}, {p['choice']} has the highest net "
                    "monetary benefit.", ""]
    rows = [[st, *(f"{r['time_in_state'][st]:.2f}" for r in p["results"])] for st in p["states"]]
    out += [f"Expected time in each state ({s['time_units']}, undiscounted):", ""]
    out += md.table(["State", *(r["strategy"] for r in p["results"])], rows)
    gaps = []
    if p["missing_cost"]:
        gaps.append(f"no cost for {', '.join(p['missing_cost'])} (counted as 0)")
    if p["missing_utility"]:
        gaps.append(f"no utility for {', '.join(p['missing_utility'])} (counted as 0)")
    if gaps:
        out += ["Note: " + "; ".join(gaps) + ".", ""]
    return out


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = [("markov-trace", {})]
    if p.get("incremental"):
        out.append(("markov-ce", {}))
    return out


def _claims(paths, section: str) -> list[str]:
    from latris.operations import markov
    from latris.operations.markov import _money

    p = markov.analyse(root=paths.root)
    if p["problems"]:
        return [f"The Markov model is incomplete: {len(p['problems'])} structure problem(s) (e.g. "
                f"{p['problems'][0]['label']}: {p['problems'][0]['message']})"] if section == "structure" else []
    cu, ou = _units(p)
    s = p["settings"]
    claims: list[str] = []
    inc = p.get("incremental", [])
    if section == "structure":
        claims.append(f"A cohort model of {len(p['states'])} states ({', '.join(p['states'])}) over "
                      f"{s['num_cycles']} cycles of {s['cycle_length']:g} {s['time_units']}, comparing "
                      f"{', '.join(p['strategies'])}.")
    elif section == "answer":
        claims.append(markov.describe(p) + ".")
    elif section == "sensitivity":
        for r in inc:
            if r["icer"] is not None:
                claims.append(f"{r['strategy']} is worth choosing over {r['versus']} only if a unit of {ou} is worth "
                              f"more than {_money(r['icer'], cu)} — its ICER is the threshold.")
        if p["unverified_transitions"]:
            claims.append(f"Transition probabilities not verified: {', '.join(p['unverified_transitions'][:6])}.")
    elif section == "implications":
        dominated = [r for r in inc if r["status"] != "frontier"]
        if dominated:
            claims.append("Never cost-effective, whatever the willingness to pay: "
                          + ", ".join(f"{r['strategy']} ({r['status']})" for r in dominated) + ".")
        if p.get("choice"):
            claims.append(f"At {_money(s['wtp'], cu)} per {ou}, choose {p['choice']}.")
        elif inc and s["wtp"] is None:
            claims.append("Set a willingness to pay (`latris markov settings --wtp`) to name the strategy to choose.")
    elif section == "gaps":
        if p["missing_cost"] or p["missing_utility"]:
            claims.append("States counted as costing nothing or worth nothing because no value is recorded: "
                          + ", ".join(sorted(set(p["missing_cost"]) | set(p["missing_utility"]))) + ".")
        if p["unsourced_transitions"]:
            claims.append(f"Transitions with no source: {', '.join(p['unsourced_transitions'][:6])}.")
    return claims


def _mermaid(paths, entities, edges) -> str:
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations import markov

    m = markov.load(root=paths.root)
    if m.problems or not m.states:
        return ""
    alias = {st: f"s{i}" for i, st in enumerate(m.states)}
    leaving = {a for a, _ in m.edges.values()}
    lines = ["flowchart LR"]
    for st in m.states:
        text = _mermaid_text(m.labels[st])
        lines.append(f'    {alias[st]}(["{text}"])' if st in leaving else f'    {alias[st]}[["{text}"]]')
    for e, (a, b) in m.edges.items():
        base = m.prob(e, None)
        label = f"{base.probability:.3g}" if base else "by strategy"
        lines.append(f'    {alias[a]} -->|"{label}"| {alias[b]}')
    return "\n".join(lines) + "\n"


def _problems(root: Path) -> list:
    from latris.operations import markov

    return markov.structure_problems(root=root)


def _check(block, known, outcome: str | None) -> list[str]:
    from latris.operations.build import split_link

    problems = [f"markov element: no factor named {x.node!r}" for x in block.elements if not known(x.node)]
    for t in block.transitions:
        ends = split_link(t.link)
        if ends is None:
            problems.append(f"markov transition {t.link!r}: write it as 'From state -> To state'")
        else:
            problems += [f"markov transition: no factor named {n!r}" for n in ends if not known(n)]
    names = [x.state for x in block.rewards] + [x.state for x in block.start]
    names += [x.strategy for x in [*block.transitions, *block.rewards] if x.strategy]
    problems += [f"markov: no factor named {n!r}" for n in names if not known(n)]
    return problems


def _apply(block, verified_by: str, root: Path) -> int:
    from latris.operations import markov

    n = 0
    for e in block.elements:
        markov.set_element(e.node, e.type, root=root)
        n += 1
    if block.settings:
        markov.set_settings(root=root, **block.settings.model_dump(exclude_none=True))
        n += 1
    for t in block.transitions:
        markov.set_transition(t.link, t.probability, strategy=t.strategy,
                              origin=t.origin or default_origin(verified_by), source_id=t.source,
                              verification=spec_verification(t.verified, verified_by), notes=t.notes, root=root)
        n += 1
    for r in block.rewards:
        fields = {k: v for k, v in (("cost", r.cost), ("utility", r.utility), ("notes", r.notes)) if v is not None}
        markov.set_reward(r.state, strategy=r.strategy, **fields, origin=r.origin or default_origin(verified_by),
                          source_id=r.source, verification=spec_verification(r.verified, verified_by), root=root)
        n += 1
    for s in block.start:
        markov.set_start(s.state, s.proportion, root=root)
        n += 1
    return n


def _export(paths, labels: dict[str, str]):
    from latris.operations import markov
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.build_spec import (
        SpecMarkov,
        SpecMarkovElement,
        SpecMarkovReward,
        SpecMarkovSettings,
        SpecMarkovStart,
        SpecMarkovTransition,
    )

    roles = markov.get_elements(root=paths.root)
    elements = sorted((SpecMarkovElement(node=labels[k], type=v) for k, v in roles.items() if k in labels),
                      key=lambda x: (x.type, x.node))
    if not elements:
        return None
    ends = {e.id: (e.from_id, e.to_id) for e in load_model(Substrate, paths.conceptual_yaml).edges}
    trans = [SpecMarkovTransition(link=f"{labels[ends[t.target_id][0]]} -> {labels[ends[t.target_id][1]]}",
                                  probability=t.probability, strategy=labels.get(t.strategy) if t.strategy else None,
                                  notes=t.notes, source=t.source_id, origin=t.origin,
                                  verified=t.verification == "human-verified")
             for t in markov.get_transitions(root=paths.root).entries
             if t.target_id in ends and all(x in labels for x in ends[t.target_id])]
    rewards = [SpecMarkovReward(state=labels[r.target_id], strategy=labels.get(r.strategy) if r.strategy else None,
                                cost=r.cost, utility=r.utility, notes=r.notes, source=r.source_id, origin=r.origin,
                                verified=r.verification == "human-verified")
               for r in markov.get_rewards(root=paths.root).entries if r.target_id in labels]
    start = [SpecMarkovStart(state=labels[s.target_id], proportion=s.proportion)
             for s in markov.get_start(root=paths.root).entries if s.target_id in labels]
    st = markov.get_settings(root=paths.root)
    settings = SpecMarkovSettings(**st.model_dump(exclude={"model_type", "set_by", "rationale"}))
    return SpecMarkov(elements=elements, settings=settings, transitions=trans, rewards=rewards, start=start)


def _run(a, root: Path) -> str:
    from latris.operations import markov

    payload = markov.analyse(root=root)
    if payload["problems"]:
        raise ValueError(markov.describe(payload))
    return markov.record(payload, root=root)[1]


def _definition(payload: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    return make_analysis(kind="markov_analyse")



# How a chat assistant runs each analysis (latris-app generates the tool from the manifest).
_TOOLS = {
    'markov-analysis': ('analyse_markov',
        'Run the Markov cohort model: state occupancy per cycle, discounted costs and outcomes per '
        'strategy, and the incremental analysis (ICERs, dominance, the strategy to choose at the '
        'willingness to pay). Recorded with charts.'),
}


# How a chat assistant writes this type's build-spec block (latris-app generates each operation).
_CHAT_OPS = (
    ChatOp('set_markov_settings', ('settings',),
        'Cycles, cycle length, discount rates, half-cycle correction, willingness to pay, and cost '
        'and outcome units.'),
    ChatOp('set_markov_element', ('elements',),
        'Make a factor a health state (or other state) or a strategy.'),
    ChatOp('set_markov_transition', ('transitions',),
        "The probability per cycle of moving 'From -> To' (optionally for one strategy)."),
    ChatOp('set_markov_reward', ('rewards',),
        "A state's cost and utility per cycle (optionally for one strategy)."),
    ChatOp('set_markov_start', ('start',),
        'The share of the cohort starting in a state.'),
)

register(Formalism(
    model_type="markov",
    outcome_role=None,
    outcome_refusal=("A Markov model's results are each strategy's costs and outcomes, not one outcome factor: give "
                     "factors the element 'state' or 'strategy' (latris markov element <factor> state)."),
    outcome_ids=lambda paths: set(),
    structure_problems=_problems,
    validators={
        "mk_states": ("mk_too_few_states", "mk_no_start", "mk_start_sum"),
        "mk_transitions": ("mk_no_transitions", "mk_bad_transition", "mk_prob_sum"),
    },
    claims=_claims,
    centrality=False,
    own_implications=True,
    sensitivity_fallback="Complete the model to see the thresholds at which the choice changes.",
    results=(ResultKind(tool=ChatTool(*_TOOLS['markov-analysis']),
                        kind="markov-analysis", title="Markov cohort model: costs, outcomes and cost-effectiveness",
                        render=_render, analysis="markov_analyse", run=_run, definition=_definition,
                        charts=_charts, chart_kinds=("markov-trace", "markov-ce")),),
    spec_field="markov",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    chat_ops=_CHAT_OPS,
    mermaid=_mermaid,
    cli=("latris.cli.markov_cmd", "markov"),
    routes="latris.server.routes.markov",
))
