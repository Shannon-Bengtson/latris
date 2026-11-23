"""System dynamics: constants and stocks' starting values in; each variable's run, or a measure of it, out.

The model is compiled once (``sd.compile_project``); a call replaces values on a copy that shares the
compiled equations (``sd_inference.with_values``) and simulates. The clock is the model's own.
"""

from __future__ import annotations

from typing import Any

from latris.operations import sd as sd_ops
from latris.operations import sd_inference
from latris.operations._units import Quantity
from latris.operations.predictors import Candidate, Run
from latris.operations.sd_sensitivity import measure, parse_metric


class SDPredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        self.model: sd_inference.SDModel | None = None
        self.problems: list[str] = []
        try:
            self.model = sd_ops.compile_project(root=paths.root)
        except ValueError as exc:
            self.problems = [str(exc)]
        self.outcome = sd_ops.get_settings(root=paths.root).outcome

    def inputs(self) -> list[Candidate]:
        m = self.model
        if m is None:
            return []
        consts = [Candidate(i, m.labels[i], ("value",), units=m.unit_text.get(i) or str(q.units),
                            value=float(q.magnitude), role="constant", suggested=True)
                  for i, q in sorted(m.constants.items(), key=lambda t: m.labels[t[0]].casefold())
                  if i not in m.hidden]
        stocks = [Candidate(i, m.labels[i], ("value",), units=m.unit_text.get(i) or str(m.stock_units[i]),
                            value=m.initial[i], role="stock (starting value)")
                  for i in sorted(m.stocks, key=lambda i: m.labels[i].casefold()) if i not in m.hidden]
        return consts + stocks

    def outputs(self) -> list[Candidate]:
        m = self.model
        if m is None:
            return []
        shown = [i for i in [*m.stocks, *m.order] if i not in m.hidden]
        return [Candidate(i, m.labels[i], ("series", "value"), units=m.unit_text.get(i), role=m.roles.get(i, ""),
                          needs_metric=True, suggested=i == self.outcome or (not self.outcome and i in m.stocks),
                          time_units=str(m.settings.time_units),
                          time_range=(float(m.settings.initial_time), float(m.settings.final_time)))
                for i in shown]

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        m = self.model
        assert m is not None
        constants = {i: Quantity(float(v), m.constants[i].units) for i, v in values.items() if i in m.constants}
        initial = {i: float(v) for i, v in values.items() if i in m.stock_units}
        result = sd_inference.simulate(sd_inference.with_values(m, constants=constants, initial=initial))
        if not result.success:
            raise ValueError(f"the simulation failed: {result.message}")
        out: dict[str, Any] = {}
        for o in outputs:
            series = result.series[o.target_id]
            if o.kind == "series":
                out[o.name] = {"times": list(result.times), "values": list(series), "time_units": result.time_units}
            else:
                metric, at = parse_metric(o.metric or "final")
                out[o.name] = measure(result.times, series, metric, at)
        return Run(out, [(None, w) for w in result.warnings])


def build(paths) -> SDPredictor:  # noqa: ANN001
    return SDPredictor(paths)
