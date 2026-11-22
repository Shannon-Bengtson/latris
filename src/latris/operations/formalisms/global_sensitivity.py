"""Global sensitivity (Sobol indices, Morris screening) as an analysis layer (``operations/global_sensitivity``).

Not a model type: it adds a result to each type whose inputs can carry a range — fault trees, bow-ties, event
trees, decision trees, Markov models and system dynamics — read from the same ranges their Monte Carlo or
probabilistic sensitivity analysis uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import Analysis, ChatTool, ResultKind, register_analysis

_TYPES = {
    "fault_tree": ("ft_gsa", "gsa_fault_tree", "Fault tree"),
    "bow_tie": ("bt_gsa", "gsa_bow_tie", "Bow-tie"),
    "event_tree": ("et_gsa", "gsa_event_tree", "Event tree"),
    "decision_tree": ("dt_gsa", "gsa_decision_tree", "Decision tree"),
    "markov": ("markov_gsa", "gsa_markov", "Markov cohort model"),
    "sd": ("sd_gsa", "gsa_sd", "System dynamics"),
}
_TOOL = ("Which uncertain inputs does the {what}'s result depend on, alone and through interactions? Varies every "
         "input with a range together: Sobol indices (method 'sobol': the share of the result's variance each "
         "explains alone and in total) or a cheaper Morris screen ('morris'). n, seed, output (the result to "
         "headline){sd}. Recorded with a chart.")


def _g(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else f"{x:.3g}"


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations import global_sensitivity as gs

    out = [md.esc(gs.describe(p)) + ".", ""]
    main = next(o for o in p["outputs"] if o["output"] == p["primary"])
    if p["method"] == "sobol":
        rows = [[r["input"], f"{_g(r['ST'], True)} ± {_g(r['ST_conf'], True)}",
                 f"{_g(r['S1'], True)} ± {_g(r['S1_conf'], True)}", f"{r['distribution']} (5th–95th: "
                 f"{_g(r['p5'])} – {_g(r['p95'])})", "unverified" if r["weak"] else "verified"]
                for r in main["indices"][:md.MAX_ROWS]]
        out += [f"Share of the variance of {md.esc(p['primary'])} each input explains — in total (with its "
                "interactions) and alone — with 95% bootstrap intervals:", ""]
        out += md.table(["Input", "Total (ST)", "Alone (S1)", "Range", "Range checked"], rows)
    else:
        rows = [[r["input"], _g(r["mu_star"]), _g(r["mu_star_conf"]), _g(r["sigma"]),
                 f"{r['distribution']} (5th–95th: {_g(r['p5'])} – {_g(r['p95'])})",
                 "unverified" if r["weak"] else "verified"] for r in main["indices"][:md.MAX_ROWS]]
        out += [f"Elementary effects on {md.esc(p['primary'])}, in its units per unit of each input's quantile: "
                "μ* ranks influence, a σ near or above μ* means interaction or a non-linear effect.", ""]
        out += md.table(["Input", "μ*", "± (95%)", "σ", "Range", "Range checked"], rows)
    if p["fixed"]:
        out += ["Held at their point value (no range given): " + md.esc(", ".join(p["fixed"][:md.MAX_ROWS * 2]))
                + ".", ""]
    out += [md.esc(n) + "." for n in p["notes"]]
    how = f"Sobol, {p['n']} base samples" if p["method"] == "sobol" else f"Morris, {p['n']} trajectories"
    out += [f"{p['runs']} model runs ({how}), seed {p['seed']}. Inputs vary independently, each over its whole "
            "distribution.", ""]
    return out


def _claims(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations import global_sensitivity as gs

    out["sensitivity"].append(gs.describe(p) + ".")
    main = next(o for o in p["outputs"] if o["output"] == p["primary"])
    rank = "ST" if p["method"] == "sobol" else "mu_star"
    top = [r for r in main["indices"][:2] if r[rank]]
    weak = [r["input"] for r in top if r["weak"]]
    if weak:
        out["open_questions"].append(f"The uncertainty in {p['primary']} comes mostly from ranges nobody has "
                                     f"checked: {', '.join(weak)}. Narrowing them is where evidence pays most.")
    if p["fixed"]:
        out["assumptions_limitations"].append(
            f"The global sensitivity analysis treats {len(p['fixed'])} input(s) as exact (no range given); their "
            "share of the uncertainty isn't measured.")


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("gsa-indices", {})] if p.get("outputs") else []


def _kind(model_type: str) -> ResultKind:
    from latris.operations.global_sensitivity import KINDS

    analysis, tool, what = _TYPES[model_type]

    def run(a, root: Path) -> str:
        from latris.operations import global_sensitivity as gs

        payload = gs.analyse(model_type, method=a.method or "sobol", n=a.n, seed=1234 if a.seed is None else a.seed,
                             output=a.output, variable=a.variable, metric=a.metric, root=root)
        return gs.record(payload, root=root)[1]

    def definition(p: dict[str, Any]):
        from latris.schema.build_spec import make_analysis

        return make_analysis(kind=analysis, method=p["method"], n=p["n"], seed=p["seed"], output=p["primary"],
                             variable=p.get("variable"), metric=p.get("metric"))

    sd_opts = "; variable and metric (final, peak, peak-time, min, mean, total, at:T)" if model_type == "sd" else ""
    return ResultKind(tool=ChatTool(tool, _TOOL.format(what=what.lower(), sd=sd_opts)), kind=KINDS[model_type],
                      title=f"{what}: global sensitivity",
                      title_for=lambda p: f"{what}: global sensitivity of {p['primary']}",
                      render=_render, analysis=analysis, run=run, definition=definition, claims=_claims,
                      charts=_charts, chart_kinds=("gsa-indices",))


for _mt in _TYPES:
    register_analysis(Analysis(model_type=_mt, result=_kind(_mt)))
