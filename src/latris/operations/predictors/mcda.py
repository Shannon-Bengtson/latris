"""MCDA: criteria's weights and options' scores in; each option's overall value (0–100, as the analysis
reports it) and the top option (a ``choice``) out.

The calculation is the analysis's own: partial values on each criterion's scale (``mcda.values``), weighted
by the normalised swing weights. A criterion without a fixed scale is scaled to the options' own range
(*local*), so a changed score on it can move every option's value; a run that changes one says so.
"""

from __future__ import annotations

from typing import Any

from latris.operations.predictors import MODEL, Candidate, Run, split_key

WEIGHT, TOTAL, BEST = "mcda:weight", "mcda:total", "mcda:best"


def score_cell(criterion: str) -> str:
    return f"mcda:score:{criterion}"


class MCDAPredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        from latris.operations import mcda

        self._mcda = mcda
        self.m = m = mcda.load(root=paths.root)
        self.problems = ["the MCDA is incomplete; `latris mcda check` lists what's missing"] if m.problems else []

    def _units(self, c: str) -> str:
        return self.m.settings[c].units or "dimensionless"

    def inputs(self) -> list[Candidate]:
        m = self.m
        if m.problems:
            return []
        lab = m.labels
        out = [Candidate(c, f"{lab[c]} (weight)", ("value",), units="dimensionless", value=m.settings[c].weight,
                         valid_min=0.0, role="criterion (swing weight)", suggested=True, cell=WEIGHT, exact=True)
               for c in m.criteria]
        for o in m.options:
            for c in m.criteria:
                s = m.settings[c]
                lo, hi = sorted((s.worst, s.best)) if s.worst is not None and s.best is not None else (None, None)
                out.append(Candidate(o, f"{lab[o]} on {lab[c]}", ("value",), units=self._units(c),
                                     value=m.scores[(o, c)].value, valid_min=lo, valid_max=hi,
                                     role="option (score on a criterion)", cell=score_cell(c)))
        return out

    def outputs(self) -> list[Candidate]:
        m = self.m
        if m.problems:
            return []
        return [*(Candidate(o, f"{m.labels[o]} (overall value)", ("value",), units="dimensionless",
                            role="overall value, 0–100", suggested=True, cell=TOTAL) for o in m.options),
                Candidate(MODEL, "Top option", ("choice",), states=tuple(m.labels[o] for o in m.options),
                          role="the option with the highest overall value", suggested=True, cell=BEST)]

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        m, lab = self.m, self.m.labels
        weight = {c: m.settings[c].weight for c in m.criteria}
        x = {k: s.value for k, s in m.scores.items()}
        warnings: list[tuple[str | None, str]] = []
        local_changed: set[str] = set()
        for k, v in values.items():
            target, cell = split_key(k)
            if cell == WEIGHT:
                weight[target] = float(v)
            else:
                c = (cell or "").split(":", 2)[2]
                x[(target, c)] = float(v)
                if m.settings[c].worst is None:
                    local_changed.add(c)
        tot = sum(weight.values())  # type: ignore[arg-type]
        if tot <= 0:
            raise ValueError("at least one criterion needs a weight above 0")
        w = {c: weight[c] / tot for c in m.criteria}  # type: ignore[operator]
        direction = {c: m.settings[c].direction for c in m.criteria}
        scale = {c: (m.settings[c].worst, m.settings[c].best) if m.settings[c].worst is not None else None
                 for c in m.criteria}
        v, _, notes = self._mcda.values(x, m.options, m.criteria, direction, scale)  # type: ignore[arg-type]
        total = {o: 100 * sum(w[c] * v[(o, c)] for c in m.criteria) for o in m.options}
        for c in sorted(local_changed, key=lambda c: lab[c]):
            warnings.append((None, f"{lab[c]} has no fixed scale, so it is scaled to the options' own range: a "
                                   "changed score on it moves every option's value. Fix its scale (`latris mcda "
                                   "criterion --worst --best`) to compare runs"))
        for n in notes:
            if n.startswith("outside:"):
                _, o, c = n.split(":")
                warnings.append((None, f"{lab[o]}'s score on {lab[c]} is outside the criterion's scale: it counts as "
                                       "the end of the scale"))
        best = min(m.options, key=lambda o: (-total[o], lab[o]))
        out = {o.name: lab[best] if o.cell == BEST else total[o.target_id] for o in outputs}
        return Run(out, warnings)


def build(paths) -> MCDAPredictor:  # noqa: ANN001
    return MCDAPredictor(paths)
