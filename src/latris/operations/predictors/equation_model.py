"""Equation model: inputs and parameters in, every formula's value out (``equation_model.compute``)."""

from __future__ import annotations

from typing import Any

from latris.operations import equation_model as eq
from latris.operations._sd_eval import EquationError
from latris.operations.predictors import Candidate, Run


class EquationPredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        self.m = eq.load(root=paths.root)
        self.problems = [f"{self.m.labels.get(p.target_id or '', 'the model')}: {p.message}" for p in self.m.problems]

    def inputs(self) -> list[Candidate]:
        m = self.m
        ordered = sorted(m.values, key=lambda i: (m.roles[i] != "input", m.labels[i].casefold()))
        return [Candidate(i, m.labels[i], ("value",), units=m.values[i].units, value=m.values[i].value,
                          valid_min=m.values[i].valid_min, valid_max=m.values[i].valid_max, role=m.roles[i],
                          suggested=m.roles[i] == "input") for i in ordered]

    def outputs(self) -> list[Candidate]:
        m = self.m
        ordered = m.outputs + [i for i in m.order if i not in m.outputs]
        return [Candidate(i, m.labels[i], ("value",), units=m.formulas[i].units, role=m.roles[i],
                          suggested=m.roles[i] == "output") for i in ordered if i in m.formulas]

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        try:
            computed = eq.compute(self.m, {k: float(v) for k, v in values.items()})
        except EquationError as exc:
            raise ValueError(str(exc)) from exc
        warnings: list[tuple[str | None, str]] = []
        ids = {label: i for i, label in self.m.labels.items() if i in self.m.values}
        for o in eq.outside_range(self.m, computed):
            lo = "" if o["valid_min"] is None else f"{o['valid_min']:g}"
            hi = "" if o["valid_max"] is None else f"{o['valid_max']:g}"
            warnings.append((ids[o["quantity"]], f"{o['quantity']} = {eq.fmt(o['value'], o['units'])} is outside "
                             f"its valid range in the model ({lo}–{hi}): the result is an extrapolation"))
        return Run({o.name: computed[o.target_id] for o in outputs}, warnings)


def build(paths) -> EquationPredictor:  # noqa: ANN001
    return EquationPredictor(paths)
