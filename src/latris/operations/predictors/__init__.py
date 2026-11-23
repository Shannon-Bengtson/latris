"""What each model type offers a contract, and how it runs on a caller's inputs — one module per type.

``Formalism.predictor`` names a module here with ``build(paths) -> Predictor``. A :class:`Predictor` is the
model loaded and compiled once: it lists what could be an input and an output (:class:`Candidate`), and
``run`` computes the outputs for a set of input values. ``run`` is pure — nothing is read or written — so
one predictor serves any number of calls (``operations/predict.py``).

A model type that has no forward calculation to offer (a theory of change, an argument map) has no
predictor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Candidate:
    """Something a model could expose: as an input (settable) or an output (computed)."""

    target_id: str
    label: str
    kinds: tuple[str, ...]  # input: ("value",) or ("state",); output: any of "value", "series", "distribution"
    units: str | None = None  # the model's own units
    value: float | str | None = None  # an input's own value in the model (what a run uses by default)
    valid_min: float | None = None
    valid_max: float | None = None
    states: tuple[str, ...] = ()
    role: str = ""  # what it is in the model ("input", "constant", "stock (starting value)"…)
    needs_metric: bool = False  # output: a "value" is a metric of its time series (final, peak…)
    suggested: bool = False  # part of the contract `contract init` drafts
    time_units: str | None = None  # output with a run behind it: the clock's units (peak-time, total)
    time_range: tuple[float, float] | None = None  # … and the time the run covers (at:T must be inside it)


@dataclass
class Run:
    """What one call computed: each requested output by name, and anything the caller should know."""

    outputs: dict[str, Any]
    # (the factor it is about, or None; the warning). One about a factor that is a contract input is dropped:
    # the contract's own range check has already said it.
    warnings: list[tuple[str | None, str]] = field(default_factory=list)


class Predictor(Protocol):
    problems: list[str]  # why the model can't run yet; empty when it can

    def inputs(self) -> list[Candidate]: ...

    def outputs(self) -> list[Candidate]: ...

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        """``values``: input target id → value in the model's own units (or a state's name); ``modes``:
        target id → "observe" | "set" for states; ``outputs``: the contract's outputs to compute."""
        ...
