"""Monte Carlo uncertainty, shared by the fault-tree, bow-tie and event-tree plugins (``operations/risk_uncertainty``).

One result kind per type, the same report section, claims and build-spec handling; each plugin adds
:func:`result_kind` to its results and calls the spec helpers from its own check, apply and export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import ResultKind, default_origin, spec_verification

_ANALYSIS = {"fault_tree": "ft_monte_carlo", "bow_tie": "bowtie_monte_carlo", "event_tree": "et_monte_carlo"}
_TITLE = {"fault_tree": "Fault tree: uncertainty (Monte Carlo)", "bow_tie": "Bow-tie: uncertainty (Monte Carlo)",
          "event_tree": "Event tree: uncertainty (Monte Carlo)"}


def _render(p: dict[str, Any]) -> list[str]:
    from latris.exporters import md
    from latris.operations.risk_uncertainty import describe

    def g(x):
        return "—" if x is None else f"{x:.3g}"

    out = [md.esc(describe(p)) + ".", ""]
    rows = [[o["output"], g(o["point"]), g(o["mean"]), g(o["p5"]), g(o["p50"]), g(o["p95"])]
            for o in p["outputs"][:md.MAX_ROWS]]
    out += md.table(["Result", "Point estimate", "Mean", "5th pct", "Median", "95th pct"], rows)
    if p["drivers"]:
        rows = [[d["input"], f"{d['distribution']} (5th–95th: {g(d['p5'])} – {g(d['p95'])})",
                 "—" if d["spearman"] is None else f"{d['spearman']:+.2f}",
                 md.esc(d["reason"]) or "—", "unverified" if d["weak"] else "verified"]
                for d in p["drivers"][:md.MAX_ROWS]]
        out += [f"What drives the spread in {p['primary']}: each uncertain input's range and its rank correlation "
                "with the result.", ""]
        out += md.table(["Input", "Range", "Rank correlation", "Why this range", "Range checked"], rows)
    if p["fixed"]:
        out += ["Held at their point value (no range given): " + md.esc(", ".join(p["fixed"][:md.MAX_ROWS * 2])) + ".",
                ""]
    out += [f"{p['runs']} runs, {'Latin hypercube' if p['sampling'] == 'lhs' else 'random'} sampling, seed "
            f"{p['seed']}. Inputs are sampled independently, each once per run.", ""]
    return out


def _claims(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.risk_uncertainty import describe

    out["sensitivity"].append(describe(p) + ".")
    main = next(o for o in p["outputs"] if o["output"] == p["primary"])
    if main["mean_over_point"] and main["mean_over_point"] > 1.2:
        out["confidence_assessment"].append(
            f"Taking the uncertainty into account, the expected {p['primary']} is {main['mean_over_point']:.2g} "
            f"times the point estimate ({main['mean']:.3g} against {main['point']:.3g})."
        )
    weak = [d["input"] for d in p["drivers"][:3] if d["weak"] and d["spearman"] and abs(d["spearman"]) >= 0.3]
    if weak:
        out["open_questions"].append(
            f"The ranges driving most of the uncertainty in {p['primary']} haven't been checked: {', '.join(weak)}."
        )
    if p["fixed"]:
        out["assumptions_limitations"].append(
            f"The Monte Carlo treats {len(p['fixed'])} input(s) as exact (no range given), so the spread it shows "
            "is a lower bound on the real uncertainty."
        )


def _charts(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("mc-strip", {})] if p.get("outputs") else []


def result_kind(model_type: str) -> ResultKind:
    from latris.operations.risk_uncertainty import KINDS

    def run(a, root: Path) -> str:
        from latris.operations import risk_uncertainty as ru

        payload = ru.monte_carlo(model_type, runs=a.runs or 2000, seed=a.seed if a.seed is not None else 1234,
                                 sampling=a.sampling or "lhs", output=a.target, root=root)
        return ru.record(payload, root=root)[1]

    def definition(p: dict[str, Any]):
        from latris.schema.build_spec import SpecAnalysis

        return SpecAnalysis(kind=_ANALYSIS[model_type], runs=p["runs"], seed=p["seed"],  # type: ignore[arg-type]
                            sampling=p["sampling"], target=p["primary"])

    return ResultKind(kind=KINDS[model_type], title=_TITLE[model_type], render=_render,
                      analysis=_ANALYSIS[model_type], run=run, definition=definition, claims=_claims,
                      charts=_charts)


# ── build spec ───────────────────────────────────────────────────────


def spec_check(where: str, entries, known) -> list[str]:
    names = [n for u in entries for n in (u.node, *u.given)]
    return [f"{where} uncertainty: no factor named {n!r}" for n in names if not known(n)]


def spec_apply(model_type: str, entries, verified_by: str, root: Path) -> int:
    from latris.operations import risk_uncertainty as ru

    for u in entries:
        ru.set_uncertainty(model_type, u.node, u.distribution, dict(u.params), given=list(u.given.items()) or None,
                           reason=u.reason, source_id=u.source, origin=u.origin or default_origin(verified_by),
                           verification=spec_verification(u.verified, verified_by), root=root)
    return len(entries)


def spec_export(model_type: str, paths, labels: dict[str, str]) -> list:
    from latris.operations import risk_uncertainty as ru
    from latris.schema.build_spec import SpecRiskUncertainty

    out = []
    for e in ru.specs(model_type, paths).values():
        if e.target_id not in labels:
            continue
        parts = (e.parameter_cell_id or "").split(":", 2)
        given = dict(x.split("=", 1) for x in parts[2].split(",")) if len(parts) == 3 and parts[2] else {}
        if any(h not in labels for h in given):
            continue
        out.append(SpecRiskUncertainty(node=labels[e.target_id], distribution=e.distribution,  # type: ignore[arg-type]
                                       params=dict(e.params), given={labels[h]: a for h, a in given.items()},
                                       reason=e.reason, source=e.source_id, origin=e.origin,
                                       verified=e.verification == "human-verified"))
    return sorted(out, key=lambda u: (u.node, sorted(u.given.items())))
