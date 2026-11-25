"""What each model type offers a contract, and how it runs on a caller's inputs — one module per type.

``Formalism.predictor`` names a module here with ``build(paths) -> Predictor``. A :class:`Predictor` is the
model loaded and compiled once: it lists what could be an input and an output (:class:`Candidate`), and
``run`` computes the outputs for a set of input values. ``run`` is pure — nothing is read or written — so
one predictor serves any number of calls (``operations/predict.py``).

A candidate is identified by its factor and, where the factor holds several parameters or results, its
``cell`` (``markov:transition:<strategy>``: the vocabulary uncertainty ranges use). :func:`key` joins the
two, and ``run`` takes its values and modes by that key: the factor's id alone when there is no cell.

A model type that has no forward calculation to offer (a theory of change, an argument map) has no
predictor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


def key(target_id: str, cell: str | None = None) -> str:
    """How ``run`` addresses one parameter: ``target_id``, or ``target_id|cell``."""
    return f"{target_id}|{cell}" if cell else target_id


def split_key(k: str) -> tuple[str, str | None]:
    target, _, cell = k.partition("|")
    return target, cell or None


@dataclass(frozen=True)
class Candidate:
    """Something a model could expose: as an input (settable) or an output (computed)."""

    target_id: str
    label: str
    kinds: tuple[str, ...]  # input: ("value",) or ("state",); output: any of "value", "series", "distribution",
    # "choice"
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
    cell: str | None = None  # which of the factor's parameters or results, when it has several
    exact: bool = False  # input: a value outside the valid range is refused, not warned (a probability)

    @property
    def key(self) -> str:
        return key(self.target_id, self.cell)


@dataclass
class Run:
    """What one call computed: each requested output by name, and anything the caller should know."""

    outputs: dict[str, Any]
    # (the key (:func:`key`) of the input it is about, or None; the warning). One about a contract input is dropped:
    # the contract's own range check has already said it.
    warnings: list[tuple[str | None, str]] = field(default_factory=list)


class Predictor(Protocol):
    problems: list[str]  # why the model can't run yet; empty when it can

    def inputs(self) -> list[Candidate]: ...

    def outputs(self) -> list[Candidate]: ...

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        """``values``: input key (:func:`key`) → value in the model's own units (or a state's name); ``modes``:
        key → "observe" | "set" for states; ``outputs``: the contract's outputs to compute."""
        ...
