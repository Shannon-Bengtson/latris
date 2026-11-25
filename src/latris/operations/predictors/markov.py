"""Markov cohort model: transition probabilities, per-cycle costs and utilities, the starting cohort and the
model's settings in; each strategy's costs and outcomes, time in each state, the cohort's trace, and (with
more than one strategy) ICERs, net monetary benefit and the best strategy out.

Cells follow the address probabilistic sensitivity analysis uses (``markov:transition:<strategy>``,
``markov:cost``…), and :meth:`MarkovPredictor.apply` is the code PSA samples through (``psa.markov_psa``).
What belongs to the model as a whole (its discount rate, the base case's totals, the best strategy) is
addressed as ``model``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from latris.operations.predictors import MODEL, Candidate, Run, split_key

_TIME_UNIT = {"days": "day", "weeks": "week", "months": "month", "years": "year"}
_SETTINGS = {  # model-level input → (label, settings field, valid range)
    "discount_rate": ("Discount rate (costs)", "discount_rate", (0.0, 1.0)),
    "outcome_discount_rate": ("Discount rate (outcomes)", "outcome_discount_rate", (0.0, 1.0)),
    "num_cycles": ("Number of cycles", "num_cycles", (1.0, 10_000.0)),
    "wtp": ("Willingness to pay", "wtp", (0.0, None)),
}
# Per strategy: (cell quantity, what it is, discounted?)
_TOTALS = (("cost", "cost"), ("outcome", "outcome"), ("cost_undiscounted", "cost, undiscounted"),
           ("outcome_undiscounted", "outcome, undiscounted"))


def cell(quantity: str, qualifier: str | None = None) -> str:
    return f"markov:{quantity}" + (f":{qualifier}" if qualifier else "")


def parse(c: str | None) -> tuple[str, str | None]:
    parts = (c or "").split(":", 2)
    return (parts[1] if len(parts) > 1 else ""), (parts[2] if len(parts) > 2 else None)


class MarkovPredictor:
    def __init__(self, m) -> None:  # noqa: ANN001 — a markov.Model
        from latris.operations import markov

        self._mk = markov
        self.m = m
        self.problems = ["the Markov model is incomplete; `latris markov check` lists what's missing"] \
            if m.problems else []
        s = m.settings
        self.cost_units = s.cost_units or "dimensionless"
        self.outcome_units = s.outcome_units or "dimensionless"
        self.icer_units = f"{self.cost_units}/{self.outcome_units}"
        self.time_units = _TIME_UNIT[s.time_units]

    def _who(self, sid: str | None) -> str:
        return f" under {self.m.labels[sid]}" if sid else ""

    def _sname(self, sid: str | None) -> str:
        return self.m.labels[sid] if sid else self._mk.BASE_CASE

    # ── what it offers ──

    def inputs(self) -> list[Candidate]:
        m = self.m
        if m.problems:
            return []
        lab = m.labels
        out = []
        for (e, sid), t in sorted(m.transitions.items(), key=lambda kv: (lab[m.edges[kv[0][0]][0]],
                                                                         lab[m.edges[kv[0][0]][1]], kv[0][1] or "")):
            a, b = m.edges[e]
            out.append(Candidate(e, f"P({lab[a]} → {lab[b]}){self._who(sid)}", ("value",), units="dimensionless",
                                 value=t.probability, valid_min=0.0, valid_max=1.0, role="transition (per cycle)",
                                 cell=cell("transition", sid), exact=True))
        for (st, sid), r in sorted(m.rewards.items(), key=lambda kv: (lab[kv[0][0]], kv[0][1] or "")):
            if r.cost is not None:
                out.append(Candidate(st, f"{lab[st]} cost{self._who(sid)}", ("value",), units=self.cost_units,
                                     value=r.cost, role="cost per cycle", suggested=True, cell=cell("cost", sid)))
            if r.utility is not None:
                out.append(Candidate(st, f"{lab[st]} utility{self._who(sid)}", ("value",), units="dimensionless",
                                     value=r.utility, valid_max=1.0, role="utility weight (per year)", suggested=True,
                                     cell=cell("utility", sid)))
        for st in m.states:
            out.append(Candidate(st, f"{lab[st]} (starting share)", ("value",), units="dimensionless",
                                 value=m.start.get(st, 0.0), valid_min=0.0, valid_max=1.0, role="starting share",
                                 cell=cell("start"), exact=True))
        s = m.settings
        for name, (label, field, (lo, hi)) in _SETTINGS.items():
            if name == "wtp" and len(m.strategy_names()) < 2:
                continue
            units = self.icer_units if name == "wtp" else "dimensionless"
            value = getattr(s, field)
            if name == "outcome_discount_rate" and value is None:
                value = s.discount_rate
            out.append(Candidate(MODEL, label, ("value",), units=units, value=value, valid_min=lo, valid_max=hi,
                                 role="setting", cell=cell(name), exact=True))
        return out

    def outputs(self) -> list[Candidate]:
        m = self.m
        if m.problems:
            return []
        strategies = m.strategy_names()
        several = len(strategies) > 1
        out = []
        for sid in strategies:
            target, name = sid or MODEL, self._sname(sid)
            for q, what in _TOTALS:
                units = self.cost_units if q.startswith("cost") else self.outcome_units
                out.append(Candidate(target, f"{name} {what}", ("value",), units=units, role=f"total {what}",
                                     suggested=q in ("cost", "outcome"), cell=cell(q)))
            if several:
                out.append(Candidate(target, f"{name} ICER", ("value",), units=self.icer_units,
                                     role="incremental cost per unit of outcome, against the next on the frontier",
                                     suggested=True, cell=cell("icer")))
                if m.settings.wtp is not None:
                    out.append(Candidate(target, f"{name} net monetary benefit", ("value",), units=self.cost_units,
                                         role="outcome × willingness to pay − cost", cell=cell("nmb")))
            for st in m.states:
                out.append(Candidate(target, f"{name}: time in {m.labels[st]}", ("value",), units=self.time_units,
                                     role="time in a state (undiscounted)", cell=cell("time_in", st)))
                out.append(Candidate(target, f"{name}: share in {m.labels[st]}", ("series",), units="dimensionless",
                                     role="the cohort's share in a state, cycle by cycle", cell=cell("trace", st)))
        if several and m.settings.wtp is not None:
            out.append(Candidate(MODEL, "Best strategy", ("choice",),
                                 states=tuple(self._sname(s) for s in strategies),
                                 role="the strategy with the highest net monetary benefit", suggested=True,
                                 cell=cell("best")))
        return out

    # ── the calculation ──

    def apply(self, values: dict[str, Any], leaving: dict[str, list[str]] | None = None):  # noqa: ANN201
        """The model with ``values`` (by input key) in place of its own. ``leaving``: for PSA's Dirichlet draws
        over a state's way out, the transition edges in the draw's order."""
        m = self.m
        transitions, rewards, start = dict(m.transitions), dict(m.rewards), dict(m.start)
        settings: dict[str, Any] = {}
        started = False
        for k, v in values.items():
            target, c = split_key(k)
            q, sid = parse(c)
            if q == "transition":
                transitions[(target, sid)] = transitions[(target, sid)].model_copy(
                    update={"probability": min(max(float(v), 0.0), 1.0)})
            elif q in ("cost", "utility"):
                rewards[(target, sid)] = rewards[(target, sid)].model_copy(update={q: float(v)})
            elif q == "leaving":
                for x, p in zip((leaving or {})[k], v, strict=False):
                    cur = transitions.get((x, sid)) or transitions[(x, None)]
                    transitions[(x, sid)] = cur.model_copy(update={"probability": p, "strategy": sid})
            elif q == "start":
                start[target], started = float(v), True
            elif q in _SETTINGS:
                v = float(v)
                if q == "num_cycles":
                    if not v.is_integer():
                        raise ValueError(f"the number of cycles is a whole number, not {v:g}")
                    v = int(v)
                settings[_SETTINGS[q][1]] = v
        if started and abs(sum(start.values()) - 1.0) > 1e-6:
            raise ValueError(f"the starting shares must sum to 1; with these inputs they sum to "
                             f"{sum(start.values()):.6g}")
        return replace(m, transitions=transitions, rewards=rewards, start=start,
                       settings=m.settings.model_copy(update=settings) if settings else m.settings)

    def _strategy(self, mm, sid: str | None) -> dict[str, Any]:  # noqa: ANN001
        P = self._mk.transition_matrix(mm, sid)[0]
        tr = self._mk._trace(mm, P)
        c = self._mk._counting(mm, sid, tr)
        return {"tr": tr, **c}

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        mm = self.apply(values)
        strategies = mm.strategy_names()
        sid_of = {(sid or MODEL): sid for sid in strategies}
        cache: dict[str | None, dict[str, Any]] = {}

        def res(sid: str | None) -> dict[str, Any]:
            if sid not in cache:
                cache[sid] = self._strategy(mm, sid)
            return cache[sid]

        wanted = {parse(o.cell)[0] for o in outputs}
        frontier: dict[str, dict[str, Any]] = {}
        if wanted & {"icer", "nmb", "best"}:
            rows = self._mk.incremental([{"strategy": self._sname(s), "cost": res(s)["cost"],
                                          "outcome": res(s)["outcome"]} for s in strategies])
            frontier = {r["strategy"]: r for r in rows}
        wtp = mm.settings.wtp
        out: dict[str, Any] = {}
        warnings: list[tuple[str | None, str]] = []
        s = mm.settings
        for o in outputs:
            q, qual = parse(o.cell)
            if q == "best":
                nmb = {self._sname(x): wtp * res(x)["outcome"] - res(x)["cost"] for x in strategies}  # type: ignore[operator]
                out[o.name] = max(nmb, key=lambda k: nmb[k])
                continue
            sid = sid_of[o.target_id]
            r = res(sid)
            if q in ("cost", "outcome", "cost_undiscounted", "outcome_undiscounted"):
                out[o.name] = r[q]
            elif q == "nmb":
                out[o.name] = wtp * r["outcome"] - r["cost"]  # type: ignore[operator]
            elif q == "icer":
                row = frontier[self._sname(sid)]
                out[o.name] = row["icer"]
                if row["icer"] is None:
                    why = {"dominated": f"it is dominated by {row['versus']}",
                           "extendedly dominated": "it is extendedly dominated"}.get(
                        row["status"], "it is the reference: the least costly strategy on the frontier")
                    warnings.append((None, f"{o.name}: no ICER, because {why}"))
            else:
                i = mm.states.index(qual)
                if q == "time_in":
                    out[o.name] = float(r["occ"][:, i].sum() * s.cycle_length)
                else:  # trace
                    out[o.name] = {"times": [k * s.cycle_length for k in range(len(r["tr"]))],
                                   "values": [float(x) for x in r["tr"][:, i]], "time_units": self.time_units}
        return Run(out, warnings)


def build(paths) -> MarkovPredictor:  # noqa: ANN001
    from latris.operations import markov

    return MarkovPredictor(markov.load(root=paths.root))
