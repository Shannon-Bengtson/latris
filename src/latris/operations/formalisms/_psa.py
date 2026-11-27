"""Probabilistic sensitivity analysis, shared by the decision-tree and Markov plugins (``operations/psa``).

One result kind per type, its report section, claims and chart; build-spec ``ranges`` handling. Each plugin
adds :func:`result_kind` to its results and calls the spec helpers from its own check, apply and export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import ChatTool, ResultKind, default_origin, spec_verification

_ANALYSIS = {"decision_tree": "dt_psa", "markov": "markov_psa"}
_TITLE = {"decision_tree": "Decision tree: probabilistic sensitivity analysis",
          "markov": "Markov cohort model: probabilistic sensitivity analysis"}
_TOOLS = {
    "decision_tree": ("psa_decision_tree",
        "How sure is the best choice? Samples every payoff, branch value and probability given a range, rolls "
        "the tree back for each sample, and gives each option's spread of expected value, how often each is "
        "best, the value of removing the parameter uncertainty (EVPI) and which inputs drive the choice (runs, "
        "seed, sampling). Recorded with a chart."),
    "markov": ("psa_markov",
        "How sure is the cost-effectiveness? Samples every transition, cost and utility given a range, reruns the "
        "cohort for each sample, and gives each strategy's spread of cost and outcome, the probabilistic ICERs, "
        "the probability each strategy is cost-effective at each willingness to pay (acceptability curve), the "
        "EVPI and which inputs drive the decision (runs, seed, sampling). Recorded with a chart."),
}


def _g(x: float | None) -> str:
    return "—" if x is None else f"{x:,.4g}"


def _drivers(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md

    if not p["drivers"]:
        return []
    rows = [[d["input"], f"{d['distribution']} (5th–95th: {_g(d['p5'])} – {_g(d['p95'])})",
             "—" if d["spearman"] is None else f"{d['spearman']:+.2f}", md.esc(d["reason"]) or "—",
             "unverified" if d["weak"] else "verified"] for d in p["drivers"][:md.MAX_ROWS]]
    return ([f"What drives the {md.esc(p['driver_target'])}: each uncertain input's range and its rank "
             "correlation with it.", ""]
            + md.table(["Input", "Range", "Rank correlation", "Why this range", "Range checked"], rows))


def _money(p: dict[str, Any], x: float) -> str:
    from latris.operations import psa

    if p["model_type"] == "decision_tree":
        from latris.operations.decision_tree import fmt

        return fmt(x, p["units"])
    return psa.money(x, p["cost_units"])


def _evppi(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md

    rows = p.get("evppi") or []
    if not rows:
        return []
    per = " per person" if p["model_type"] == "markov" else ""
    out = [f"What knowing each input exactly before choosing would be worth{per}, the rest still uncertain "
           f"(partial EVPI; all of them together: {_money(p, p['evpi'])}):", ""]
    out += md.table(["Input", "Partial EVPI"], [[r["input"], _money(p, r["evppi"])] for r in rows[:md.MAX_ROWS]])
    return out


def _footer(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md

    out = []
    if p.get("correlations"):
        out += ["Sampled together: " + "; ".join(
            f"{md.esc(c['a'])} and {md.esc(c['b'])} (rank correlation {c['rho']:+.2g}"
            + (f": {md.esc(c['reason'])}" if c["reason"] else "") + ")" for c in p["correlations"]) + ".", ""]
    if p["fixed"]:
        out += ["Held at their point value (no range given): " + md.esc(", ".join(p["fixed"][:md.MAX_ROWS * 2]))
                + ".", ""]
    out += [f"{p['runs']} runs, {'Latin hypercube' if p['sampling'] == 'lhs' else 'random'} sampling, seed "
            f"{p['seed']}. Inputs are sampled independently, each once per run.", ""]
    return out


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations import psa

    out = [md.esc(psa.describe(p)) + ".", ""]
    if p["model_type"] == "decision_tree":
        from latris.operations.decision_tree import fmt

        u = p["units"]
        rows = [[o["output"], fmt(o["point"], u), fmt(o["mean"], u), fmt(o["p5"], u), fmt(o["p95"], u),
                 f"{o['p_best']:.0%}"] for o in p["outputs"]]
        out += md.table([f"{p['decision']} — option", "Point estimate", "Mean", "5th pct", "95th pct", "Best in"],
                        rows)
        out += [f"Expected value of perfect information on the parameters: {fmt(p['evpi'], u)} — the most it is "
                "worth to remove all of this uncertainty before choosing.", ""]
    else:
        cu, ou = p["cost_units"], p["outcome_units"] or "outcome"
        rows = [[s["strategy"], psa.money(s["cost"]["mean"], cu),
                 f"{psa.money(s['cost']['p5'], cu)} – {psa.money(s['cost']['p95'], cu)}",
                 f"{s['outcome']['mean']:.3f}", f"{s['outcome']['p5']:.3f} – {s['outcome']['p95']:.3f}"]
                for s in p["strategies"]]
        out += md.table(["Strategy", "Mean cost", "Cost, 90% of runs", f"Mean {ou}", f"{ou}, 90% of runs"], rows)
        if p["incremental"]:
            rows = [[r["strategy"], r["status"],
                     (psa.money(r["icer"], cu) + f" per {ou} vs {r['versus']}") if r["icer"] is not None
                     else (f"by {r['versus']}" if r["status"] == "dominated" else "—")] for r in p["incremental"]]
            out += ["Incremental analysis on the probabilistic means:", ""]
            out += md.table(["Strategy", "Status", "ICER"], rows)
        c = p["ceac"]
        if len(c["strategies"]) > 1:
            picks = sorted({0, len(c["wtp"]) // 4, len(c["wtp"]) // 2, 3 * len(c["wtp"]) // 4, len(c["wtp"]) - 1})
            rows = [[psa.money(c["wtp"][i], cu), *(f"{c['p'][j][i]:.0%}" for j in range(len(c["strategies"]))),
                     c["frontier"][i], psa.money(c["evpi"][i], cu)] for i in picks]
            out += [f"Probability each strategy is the most cost-effective, by willingness to pay per {ou} (the "
                    "acceptability curve), the strategy with the highest expected net benefit, and the EVPI per "
                    "person:", ""]
            out += md.table([f"Willingness to pay per {ou}", *c["strategies"], "Choose", "EVPI"], rows)
        if p["rescaled_runs"]:
            out += [f"In {p['rescaled_runs']} run(s) the sampled probabilities of leaving a state summed to more "
                    "than 1 and were scaled down to 1; a Dirichlet on the state avoids this.", ""]
    return out + _evppi(p) + _drivers(p) + _footer(p)


def _claims(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations import psa

    out["sensitivity"].append(psa.describe(p) + ".")
    weak = [d["input"] for d in p["drivers"][:3] if d["weak"] and d["spearman"] and abs(d["spearman"]) >= 0.3]
    if weak:
        out["open_questions"].append(f"The ranges driving most of the uncertainty in the {p['driver_target']} "
                                     f"haven't been checked: {', '.join(weak)}.")
    if p["model_type"] == "decision_tree":
        from latris.operations.decision_tree import fmt

        if p["p_best"] < 0.8 and p["rival"]:
            out["confidence_assessment"].append(
                f"The best choice is not settled by the evidence: {p['rival']} comes out best in "
                f"{next(o['p_best'] for o in p['outputs'] if o['output'] == p['rival']):.0%} of the runs.")
        if p["evpi"] > 0:
            out["implications"].append(f"Research that removes the parameter uncertainty is worth at most "
                                          f"{fmt(p['evpi'], p['units'])}; anything costing more isn't.")
    elif p.get("choice"):
        cu = p["cost_units"]
        if p["p_cost_effective"] < 0.8:
            out["confidence_assessment"].append(
                f"{p['choice']} is the most cost-effective at the willingness to pay in only "
                f"{p['p_cost_effective']:.0%} of the runs.")
        if p["evpi"] > 0:
            out["implications"].append(f"Further research is worth at most {psa.money(p['evpi'], cu)} per person "
                                          "affected by the decision (the EVPI at the willingness to pay).")
    worth = [r for r in p.get("evppi") or [] if r["evppi"] > 0]
    if worth:
        per = " per person" if p["model_type"] == "markov" else ""
        out["implications"].append(
            f"Of the uncertain inputs, learning {worth[0]['input']} is worth most: up to {_money(p, worth[0]['evppi'])}"
            f"{per}" + (f"; next {worth[1]['input']} ({_money(p, worth[1]['evppi'])})" if len(worth) > 1 else "")
            + ". A study of anything else costing more than its partial EVPI isn't worth doing.")
    elif p.get("evppi") and p["evpi"] > 0:
        out["implications"].append(
            "No single input is worth learning on its own at this number of runs: each one's partial EVPI is "
            "within sampling noise of zero.")
    if p["fixed"]:
        out["assumptions_limitations"].append(
            f"The PSA treats {len(p['fixed'])} input(s) as exact (no range given), so the uncertainty it shows is "
            "a lower bound on the real uncertainty.")


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if p["model_type"] == "decision_tree":
        return [("mc-strip", {})] if p.get("outputs") else []
    return [("markov-ceac", {})] if len(p["ceac"]["strategies"]) > 1 else []


def result_kind(model_type: str) -> ResultKind:
    from latris.operations.psa import KINDS

    def run(a, root: Path) -> str:
        from latris.operations import psa

        return psa.record(psa.run(model_type, runs=a.runs, seed=a.seed, sampling=a.sampling, root=root),
                          root=root)[1]

    def definition(p: dict[str, Any]):
        from latris.schema.build_spec import make_analysis

        return make_analysis(kind=_ANALYSIS[model_type], runs=p["runs"], seed=p["seed"], sampling=p["sampling"])

    return ResultKind(step="analyse.uncertainty",
                      tool=ChatTool(*_TOOLS[model_type]), kind=KINDS[model_type], title=_TITLE[model_type],
                      render=_render, analysis=_ANALYSIS[model_type], run=run, definition=definition,
                      claims=_claims, charts=_charts,
                      chart_kinds=("mc-strip",) if model_type == "decision_tree" else ("markov-ceac",))


# ── build spec ───────────────────────────────────────────────────────


def spec_check(where: str, entries, known) -> list[str]:
    from latris.operations.build import split_link

    problems = []
    for r in entries:
        ends = split_link(r.target)
        names = list(ends) if ends else [r.target]
        if r.strategy:
            names.append(r.strategy)
        problems += [f"{where} range: no factor named {n!r}" for n in names if not known(n)]
    return problems


def spec_check_correlations(where: str, entries, known) -> list[str]:
    from latris.operations.build import split_link

    problems = []
    for c in entries:
        names = []
        for t in (c.target, c.other):
            ends = split_link(t)
            names += list(ends) if ends else [t]
        names += [x for x in (c.strategy, c.other_strategy) if x]
        problems += [f"{where} correlation: no factor named {n!r}" for n in names if not known(n)]
    return problems


def spec_apply_correlations(model_type: str, entries, verified_by: str, root: Path) -> int:
    from latris.operations import psa

    for c in entries:
        psa.set_correlation(model_type, c.target, c.other, c.rho, quantity=c.quantity,
                            other_quantity=c.other_quantity, strategy=c.strategy, other_strategy=c.other_strategy,
                            reason=c.reason, source_id=c.source, origin=c.origin or default_origin(verified_by),
                            verification=spec_verification(c.verified, verified_by), root=root)
    return len(entries)


def spec_export_correlations(model_type: str, paths, labels: dict[str, str]) -> list:
    from latris.operations import psa
    from latris.operations import uncertainty as unc
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.build_spec import SpecPsaCorrelation

    ends = {e.id: (e.from_id, e.to_id) for e in load_model(Substrate, paths.conceptual_yaml).edges}

    def name(key: str) -> tuple[str, str, str | None] | None:
        target, cell = key.split("|", 1)
        quantity, sid = psa.describe_cell(cell)
        if target in ends:
            a, b = ends[target]
            if a not in labels or b not in labels:
                return None
            label = f"{labels[a]} -> {labels[b]}"
        elif target in labels:
            label = labels[target]
        else:
            return None
        if sid and sid not in labels:
            return None
        return label, quantity, labels[sid] if sid else None

    out = []
    for c in unc.load(paths).correlations:
        if f"|{model_type}:" not in c.a:
            continue
        a, b = name(c.a), name(c.b)
        if a and b:
            out.append(SpecPsaCorrelation(target=a[0], quantity=a[1], strategy=a[2], other=b[0],
                                          other_quantity=b[1], other_strategy=b[2], rho=c.rho, reason=c.reason,
                                          source=c.source_id, origin=c.origin,
                                          verified=c.verification == "human-verified"))
    return sorted(out, key=lambda c: (c.target, c.other))


def spec_apply(model_type: str, entries, verified_by: str, root: Path) -> int:
    from latris.operations import psa

    for r in entries:
        psa.set_range(model_type, r.target, r.distribution, dict(r.params), quantity=r.quantity,
                      strategy=r.strategy, reason=r.reason, source_id=r.source,
                      origin=r.origin or default_origin(verified_by),
                      verification=spec_verification(r.verified, verified_by), root=root)
    return len(entries)


def spec_export(model_type: str, paths, labels: dict[str, str]) -> list:
    from latris.operations import psa
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.build_spec import SpecPsaRange

    ends = {e.id: (e.from_id, e.to_id) for e in load_model(Substrate, paths.conceptual_yaml).edges}
    out = []
    for e in psa.ranges(model_type, paths):
        quantity, sid = psa.describe_cell(e.parameter_cell_id or "")
        if e.target_id in ends:
            a, b = ends[e.target_id]
            if a not in labels or b not in labels:
                continue
            target = f"{labels[a]} -> {labels[b]}"
        elif e.target_id in labels:
            target = labels[e.target_id]
        else:
            continue
        if sid and sid not in labels:
            continue
        out.append(SpecPsaRange(target=target, quantity=quantity, strategy=labels[sid] if sid else None,
                                distribution=e.distribution, params=dict(e.params),  # type: ignore[arg-type]
                                reason=e.reason, source=e.source_id, origin=e.origin,
                                verified=e.verification == "human-verified"))
    return sorted(out, key=lambda r: (r.target, r.quantity or "", r.strategy or ""))
