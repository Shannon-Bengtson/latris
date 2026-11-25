"""Fuzzy cognitive map: factors held at an activation (a scenario) or started from one in; each factor's
activation at steady state out — the ``fcm-inference`` analysis (``analysis.fcm_steady_state``) as a call.

Activations are relative (0–1): they say how strongly a factor is driven compared with the others under the
map's signed weights, not a measured quantity. Compare scenarios; don't read the levels as amounts. A map
that doesn't settle returns where it stopped, with a warning.
"""

from __future__ import annotations

from typing import Any

from latris.operations.predictors import Candidate, Run, split_key

CLAMP, INITIAL = "fcm:clamp", "fcm:initial"


class FCMPredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        from latris.operations import formalisms
        from latris.repo.yaml_io import load_model, load_model_or_default
        from latris.schema import FloatSet, Substrate

        sub = load_model(Substrate, paths.conceptual_yaml)
        self.edges = sub.edges
        self.ids = [e.id for e in sub.entities]
        self.labels = {e.id: e.label for e in sub.entities}
        store = load_model_or_default(FloatSet, paths.view_attribute_path("fcm", "weight"))
        self.weights = {e.target_id: e.value for e in store.entries}
        weighted = [e for e in sub.edges if e.id in self.weights and e.from_id in self.labels
                    and e.to_id in self.labels]
        self.problems = [] if weighted else ["no link has an FCM weight yet (`latris fcm weight`)"]
        self.on_map = sorted({x for e in weighted for x in (e.from_id, e.to_id)},
                             key=lambda i: self.labels[i].casefold())
        self.driven = {e.to_id for e in weighted}
        self.drives = {e.from_id for e in weighted}
        plugin = formalisms.get("fcm")
        self.outcomes = plugin.outcome_ids(paths) if plugin else set()

    def inputs(self) -> list[Candidate]:
        out = []
        for i in self.on_map:
            out.append(Candidate(i, f"{self.labels[i]} (held at)", ("value",), units="dimensionless", valid_min=0.0,
                                 valid_max=1.0, role="factor held at an activation (relative, 0–1)",
                                 suggested=i not in self.driven, cell=CLAMP, exact=True))
            out.append(Candidate(i, f"{self.labels[i]} (starting activation)", ("value",), units="dimensionless",
                                 value=0.5, valid_min=0.0, valid_max=1.0, role="starting activation (relative, 0–1)",
                                 cell=INITIAL, exact=True))
        return out

    def outputs(self) -> list[Candidate]:
        ends = self.outcomes & set(self.on_map) or {i for i in self.on_map if i not in self.drives}
        return [Candidate(i, self.labels[i], ("value",), units="dimensionless",
                          role="activation at steady state (relative, 0–1)", suggested=i in ends)
                for i in self.on_map]

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        from latris.operations.fcm_inference import fcm_infer

        clamped: dict[str, float] = {}
        initial: dict[str, float] = {}
        for k, v in values.items():
            target, cell = split_key(k)
            (clamped if cell == CLAMP else initial)[target] = float(v)
        result = fcm_infer(self.edges, self.weights, self.ids,  # type: ignore[arg-type]  # an Edge has id, from_id, to_id
                           initial_activations=initial or None, clamped=clamped or None)
        warnings: list[tuple[str | None, str]] = []
        if not result.converged:
            warnings.append((None, f"the map hadn't settled after {result.iterations} steps (it may cycle): the "
                                   "activations are where it stopped, not a steady state"))
        return Run({o.name: result.activations[o.target_id] for o in outputs}, warnings)


def build(paths) -> FCMPredictor:  # noqa: ANN001
    return FCMPredictor(paths)
