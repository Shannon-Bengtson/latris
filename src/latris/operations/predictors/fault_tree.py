"""Fault tree: basic events' probabilities in; the top event's (or any gate's) probability out.

Each gate is compiled once to a binary decision diagram (``_ft_engine.build_bdd``), so a call is one exact
pass over it. Monte Carlo (``risk_uncertainty``) samples through the same :meth:`FaultTreePredictor.evaluate`.
"""

from __future__ import annotations

from typing import Any

from latris.operations import _ft_engine as engine
from latris.operations.predictors import Candidate, Run, key, split_key

CELL = "fault_tree:probability"


class FaultTreePredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        from latris.operations import fault_tree as ft

        self.tree = tree = ft.load_tree(root=paths.root)
        self.labels = tree.labels
        self.top = tree.top
        self.incomplete = bool(tree.problems or not tree.top)
        self.problems: list[str] = []
        self.leaves: list[str] = []
        self.missing: list[str] = []
        self.point: dict[str, float] = {}  # input key → the model's own probability
        self._bdds: dict[str, tuple[engine.BDD, int]] = {}
        if self.incomplete:
            self.problems = ["the fault tree is incomplete; `latris ft analyse` lists what's missing"]
            return
        self.gates = tree.engine_gates()
        self.leaves = engine.leaves_under(tree.top, self.gates)  # type: ignore[arg-type]
        self.missing = [self.labels[e] for e in self.leaves if e not in tree.probabilities]
        if self.missing:
            self.problems = [f"no probability yet for {', '.join(self.missing)}"]
        self.point = {key(e, CELL): tree.probabilities[e].probability for e in self.leaves
                      if e in tree.probabilities}

    def _gates(self) -> list[str]:
        """The top event, then every other gate in the tree, by label."""
        if self.incomplete:
            return []
        rest = sorted((g for g in self.gates if g != self.top), key=lambda g: self.labels[g].casefold())
        return [self.top, *rest]  # type: ignore[list-item]

    def inputs(self) -> list[Candidate]:
        return [Candidate(e, self.labels[e], ("value",), units="dimensionless",
                          value=self.tree.probabilities[e].probability if e in self.tree.probabilities else None,
                          valid_min=0.0, valid_max=1.0, role="basic event (probability)", suggested=True, cell=CELL,
                          exact=True)
                for e in sorted(self.leaves, key=lambda e: self.labels[e].casefold())]

    def outputs(self) -> list[Candidate]:
        return [Candidate(g, self.labels[g], ("value",), units="dimensionless",
                          role="top event (probability)" if g == self.top else "gate (probability)",
                          suggested=g == self.top) for g in self._gates()]

    def evaluate(self, x: dict[str, float], gates: list[str] | None = None) -> dict[str, float]:
        """Each gate's probability (default: the top event's) given every basic event's, by input key."""
        p = {split_key(k)[0]: v for k, v in x.items()}
        out = {}
        for g in gates or [self.top]:  # type: ignore[list-item]
            if g not in self._bdds:
                self._bdds[g] = engine.build_bdd(g, self.gates)
            bdd, node = self._bdds[g]
            out[g] = bdd.probability(node, p)
        return out

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        got = self.evaluate({**self.point, **{k: float(v) for k, v in values.items()}},
                            list(dict.fromkeys(o.target_id for o in outputs)))
        return Run({o.name: got[o.target_id] for o in outputs})


def build(paths) -> FaultTreePredictor:  # noqa: ANN001
    return FaultTreePredictor(paths)
