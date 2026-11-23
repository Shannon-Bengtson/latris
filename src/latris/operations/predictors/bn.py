"""Bayesian network: states observed or set in; the probability of each state of the outputs out.

The tables are loaded once; a call conditions on what was observed, cuts the links into what was set
(``bn.intervene``) and queries the outputs (``bn_inference.bn_infer``).
"""

from __future__ import annotations

from typing import Any

from latris.operations import bn as bn_ops
from latris.operations.bn_inference import bn_infer
from latris.operations.predictors import Candidate, Run
from latris.repo.yaml_io import load_model
from latris.schema import Substrate


class BNPredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        from latris.operations import formalisms

        self.labels = {e.id: e.label for e in load_model(Substrate, paths.conceptual_yaml).entities}
        self.states = {e.target_id: list(e.states) for e in bn_ops._load_state_spaces(paths).entries
                       if e.target_id in self.labels}
        self.tables = {k: v for k, v in bn_ops._effective_cpt_map(paths).items() if k in self.states}
        # A network can be queried as soon as it has tables; a factor still missing one is left out of it.
        self.problems = [] if self.tables else ["no factor has states and a probability table yet"]
        plugin = formalisms.get("bn")
        self.outcomes = plugin.outcome_ids(paths) if plugin else set()

    def _nodes(self) -> list[str]:
        return sorted(self.tables, key=lambda i: self.labels[i].casefold())

    def inputs(self) -> list[Candidate]:
        return [Candidate(i, self.labels[i], ("state",), states=tuple(self.states[i]), role="factor",
                          suggested=not self.tables[i].parents) for i in self._nodes()]

    def outputs(self) -> list[Candidate]:
        children = {p for t in self.tables.values() for p in t.parents}
        return [Candidate(i, self.labels[i], ("distribution",), states=tuple(self.states[i]), role="factor",
                          suggested=i in self.outcomes or (not self.outcomes and i not in children))
                for i in self._nodes()]

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        for i, state in values.items():
            if state not in self.states[i]:
                raise ValueError(f"{state!r} is not a state of {self.labels[i]} (states: {', '.join(self.states[i])})")
        do = {i: s for i, s in values.items() if modes.get(i) == "set"}
        seen = {i: s for i, s in values.items() if i not in do}
        tables = bn_ops.intervene(self.tables, self.states, do) if do else self.tables
        wanted = [o.target_id for o in outputs]
        ask = [i for i in dict.fromkeys(wanted) if i not in seen]
        try:
            marginals = bn_infer(self.states, tables, query=ask, evidence=seen or None).marginals if ask else {}
        except Exception as exc:  # noqa: BLE001 — the engine's own errors (an impossible observation, a bad table)
            raise ValueError(f"the network can't be queried with these inputs: {exc}") from exc
        out: dict[str, Any] = {}
        for o in outputs:
            if o.target_id in seen:  # what was observed is certain
                out[o.name] = {s: 1.0 if s == seen[o.target_id] else 0.0 for s in self.states[o.target_id]}
            else:
                out[o.name] = dict(marginals[o.target_id])
        return Run(out)


def build(paths) -> BNPredictor:  # noqa: ANN001
    return BNPredictor(paths)
