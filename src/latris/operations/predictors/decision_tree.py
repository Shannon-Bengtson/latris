"""Decision tree: payoffs, values along branches and chance probabilities in; each option's expected value,
the best option (a ``choice``), the tree's expected value and EVPI out.

The calculation is ``decision_tree.rollback`` on the tree with the inputs applied (:meth:`apply`), which
probabilistic sensitivity analysis (``psa.dt_psa``) samples through too.

A chance node with two branches offers one probability (the other branch takes the rest); with more, each
branch is an input, and the node's branches must still sum to 1 (they are not rescaled: that would hide a
caller's mistake). An uncertainty that recurs under several choices (the same "Demand" after each option)
is one input, applied to every node that shares it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from latris.operations.predictors import Candidate, Run, split_key
from latris.schema.decision_tree import DTBranchEntry

PAYOFF, VALUE, PROBABILITY = "decision_tree:payoff", "decision_tree:value", "decision_tree:probability"
PROBABILITIES = "decision_tree:probabilities"  # a whole chance node's (a Dirichlet draw in PSA)
EV, BEST, EVPI = "decision_tree:ev", "decision_tree:best", "decision_tree:evpi"
_TOL = 1e-6


class DecisionTreePredictor:
    def __init__(self, tree) -> None:  # noqa: ANN001 — a decision_tree.Tree
        from latris.operations import decision_tree as dt

        self._dt = dt
        self.t = t = tree
        self.problems = (["the decision tree is incomplete; `latris dt check` lists what's missing"]
                         if t.problems else [])
        self.units = t.settings.units or "dimensionless"
        self.parent = {e: n for n, kids in t.children.items() for e, _ in kids}
        _, nodes, _ = dt._groups(t) if not t.problems else ({}, {}, [])
        self.group_of = {n: u for u, ns in nodes.items() for n in ns}  # chance node → its consistent uncertainty
        self.nodes = nodes

    # ── what it offers ──

    def _siblings(self, n: str) -> list[str]:
        return self.nodes[self.group_of[n]] if n in self.group_of else [n]

    def _offered_chance_nodes(self) -> list[str]:
        """One chance node per uncertainty: the first of those that share it (setting it sets them all)."""
        t = self.t
        seen: set[str] = set()
        out = []
        for n in sorted((n for n, k in t.kind.items() if k == "chance"), key=lambda n: t.labels[n].casefold()):
            u = self.group_of.get(n)
            if u is not None and u in seen:
                continue
            if u is not None:
                seen.add(u)
            out.append(n)
        return out

    def _p_label(self, n: str, e: str, c: str) -> str:
        t = self.t
        where = "" if n in self.group_of else f" at {t.labels[n]}"
        return f"P({t.uncertainty[n]} = {t.branch_label(e, c)}){where}"

    def inputs(self) -> list[Candidate]:
        t = self.t
        if t.problems:
            return []
        out = [Candidate(n, f"{t.labels[n]} (payoff)", ("value",), units=self.units, value=t.payoffs[n].value,
                         role="terminal (payoff)", suggested=True, cell=PAYOFF)
               for n in sorted((n for n, k in t.kind.items() if k == "terminal"), key=lambda n: t.labels[n].casefold())]
        for n in self._offered_chance_nodes():
            kids = t.children[n]
            for e, c in kids[:1] if len(kids) == 2 else kids:  # of two branches, one: the other is the rest
                out.append(Candidate(e, self._p_label(n, e, c), ("value",), units="dimensionless",
                                     value=t.branches[e].probability, valid_min=0.0, valid_max=1.0,
                                     role="branch (probability)", suggested=True, cell=PROBABILITY, exact=True))
        for n in sorted((n for n, k in t.kind.items() if k in ("decision", "chance")),
                        key=lambda n: t.labels[n].casefold()):
            for e, c in t.children[n]:
                out.append(Candidate(e, f"{t.labels[n]} → {t.branch_label(e, c)} (value)", ("value",),
                                     units=self.units, value=t.branches[e].value if e in t.branches else 0.0,
                                     role="branch (value along it)", cell=VALUE))
        return out

    def _options(self) -> list[tuple[str, str]]:
        t = self.t
        return list(t.children[t.root]) if t.root and t.kind[t.root] == "decision" else []

    def outputs(self) -> list[Candidate]:
        t = self.t
        if t.problems:
            return []
        rt, opts = t.root, self._options()
        out = [Candidate(e, f"{t.branch_label(e, c)} (expected value)", ("value",), units=self.units,
                         role="option (expected value)", suggested=True, cell=EV) for e, c in opts]
        if opts:
            out.append(Candidate(rt, f"{t.labels[rt]} (best option)", ("choice",),  # type: ignore[arg-type]
                                 states=tuple(t.branch_label(e, c) for e, c in opts), role="the best option",
                                 suggested=True, cell=BEST))
        out.append(Candidate(rt, f"{t.labels[rt]} (expected value)", ("value",), units=self.units,  # type: ignore[arg-type]
                             role="the tree (expected value)", suggested=not opts, cell=EV))
        out.append(Candidate(rt, f"{t.labels[rt]} (EVPI)", ("value",), units=self.units,  # type: ignore[arg-type]
                             role="expected value of perfect information on every uncertainty", cell=EVPI))
        return out

    # ── the calculation ──

    def apply(self, values: dict[str, Any]):  # noqa: ANN201 — a decision_tree.Tree
        """The tree with ``values`` (by input key) in place of its own. A probability on one branch of a
        two-branch node gives the other the rest; a node's branches must sum to 1."""
        t = self.t
        payoffs, branches = dict(t.payoffs), dict(t.branches)
        given: dict[str, dict[str, float]] = {}  # chance node → branch edge → probability
        for k, v in values.items():
            target, cell = split_key(k)
            if cell == PAYOFF:
                payoffs[target] = payoffs[target].model_copy(update={"value": float(v)})
            elif cell == VALUE:
                br = branches.get(target)
                branches[target] = (br.model_copy(update={"value": float(v)}) if br else
                                    DTBranchEntry(target_id=target, value=float(v)))
            elif cell == PROBABILITY:
                given.setdefault(self.parent[target], {})[target] = min(max(float(v), 0.0), 1.0)
            elif cell == PROBABILITIES:
                given[target] = {e: float(p) for (e, _), p in zip(t.children[target], v, strict=True)}
        for n, ps in given.items():
            kids = [e for e, _ in t.children[n]]
            if len(kids) == 2 and len(ps) == 1:
                (e,) = ps
                ps[next(x for x in kids if x != e)] = 1.0 - ps[e]
            full = {e: ps.get(e, t.branches[e].probability or 0.0) for e in kids}
            total = sum(full.values())
            if abs(total - 1.0) > _TOL:
                raise ValueError(f"the branches from {t.labels[n]} ({t.uncertainty[n]}) must sum to 1; with these "
                                 f"inputs they sum to {total:.6g}")
            by_label = {t.branch_label(e, c): full[e] for e, c in t.children[n]}
            for s in self._siblings(n):
                for x, c in t.children[s]:
                    lab = t.branch_label(x, c)
                    if lab in by_label:
                        branches[x] = branches[x].model_copy(update={"probability": by_label[lab]})
        return replace(t, payoffs=payoffs, branches=branches)

    def _evpi(self, tree) -> tuple[float | None, str | None]:  # noqa: ANN001
        info = self._dt.evpi(tree)
        if info["all"] is not None:
            return info["all"]["evpi"], None
        if len(info["per_uncertainty"]) == 1:
            return info["per_uncertainty"][0]["evpi"], None
        if not info["per_uncertainty"]:
            return 0.0, "no uncertainty is the same under every choice, so perfect information isn't defined"
        return None, "; ".join(info["skipped"]) or "EVPI couldn't be computed"

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        t = self.apply(values)
        ev, choice = self._dt.rollback(t)
        rt = t.root
        out: dict[str, Any] = {}
        warnings: list[tuple[str | None, str]] = []
        for o in outputs:
            if o.cell == BEST:
                e = choice[rt]
                out[o.name] = t.branch_label(e, dict(t.children[rt])[e])
            elif o.cell == EVPI:
                out[o.name], why = self._evpi(t)
                if why:
                    warnings.append((None, f"{o.name}: {why}"))
            elif o.target_id == rt:
                out[o.name] = ev[rt]
            else:  # an option: what is incurred along its branch, then what follows
                child = dict(t.children[rt])[o.target_id]
                out[o.name] = (t.branches[o.target_id].value if o.target_id in t.branches else 0.0) + ev[child]
        return Run(out, warnings)


def build(paths) -> DecisionTreePredictor:  # noqa: ANN001
    from latris.operations import decision_tree as dt

    return DecisionTreePredictor(dt.load_tree(root=paths.root))
