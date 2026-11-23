"""A model's contract — the inputs a caller may give it and the outputs it promises back.

Stored with the model at ``views/contracts/<model_type>.yaml`` and committed like everything else, so a
pipeline that pins a version of the model pins its contract too (``docs/engineering/PREDICT.md``).

An **input** names one thing a caller can set: a number with units (an equation model's input, a system
dynamics constant or a stock's starting value) or one of a factor's states (a Bayesian network: observed,
or set as an intervention). An **output** names one thing the run returns: a value, a time series, or a
probability distribution over a factor's states.

Names are the interface: they are what a caller writes, so they are stable identifiers
(``flow_depth``), kept when the factor is renamed. Only intrinsic shape is enforced here; whether a target
exists, can be an input of this model type and has compatible units is ``operations/contract.check``.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from latris.schema.attributes import _Base

InputKind = Literal["value", "state"]
OutputKind = Literal["value", "series", "distribution"]
StateMode = Literal["observe", "set"]

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _name(v: str) -> str:
    if not _NAME.match(v or ""):
        raise ValueError(f"{v!r} is not a valid name: lower-case letters, digits and underscores, starting "
                         "with a letter (e.g. flow_depth)")
    return v


class ContractInput(_Base):
    """One thing a caller can set.

    ``default`` is what the run uses when the caller gives nothing: left out, the model's own value (or,
    for a state, nothing observed). ``valid_min``/``valid_max`` narrow what the contract accepts without a
    warning; left out, the model's own valid range applies where it has one.
    """

    name: str
    target_id: str
    kind: InputKind = "value"
    units: str | None = None  # kind "value": the units a bare number is read in
    mode: StateMode = "observe"  # kind "state": seen (evidence) or made so (an intervention)
    default: float | str | None = None
    valid_min: float | None = None
    valid_max: float | None = None
    required: bool = False
    description: str = ""

    _check_name = field_validator("name")(_name)

    @model_validator(mode="after")
    def _shape(self) -> ContractInput:
        if self.kind == "value":
            if not (self.units or "").strip():
                raise ValueError(f"input {self.name!r} needs units (use 'dimensionless' for a pure number)")
            if isinstance(self.default, str):
                raise ValueError(f"input {self.name!r} is a number: its default can't be text")
            if self.valid_min is not None and self.valid_max is not None and not self.valid_min < self.valid_max:
                raise ValueError(f"input {self.name!r}: the valid range needs its minimum below its maximum")
        else:
            if self.units or self.valid_min is not None or self.valid_max is not None:
                raise ValueError(f"input {self.name!r} is a state: it has no units or range")
            if self.default is not None and not isinstance(self.default, str):
                raise ValueError(f"input {self.name!r} is a state: its default is the state's name")
        if self.required and self.default is not None:
            raise ValueError(f"input {self.name!r} is required, so a default would never be used")
        return self


class ContractOutput(_Base):
    """One thing the run returns.

    ``metric`` turns a time series into a value (system dynamics): final, peak, peak-time, min, mean,
    total or at:T. A ``series`` output returns the whole run; a ``distribution`` the probability of each
    state.
    """

    name: str
    target_id: str
    kind: OutputKind = "value"
    units: str | None = None
    metric: str | None = None
    description: str = ""

    _check_name = field_validator("name")(_name)

    @model_validator(mode="after")
    def _shape(self) -> ContractOutput:
        if self.metric is not None and self.kind != "value":
            raise ValueError(f"output {self.name!r}: a metric makes a value of a series, so its kind is 'value'")
        if self.kind == "distribution" and self.units:
            raise ValueError(f"output {self.name!r} is a distribution: probabilities have no units")
        return self


class Contract(_Base):
    """The contract of one model type in a project."""

    model_type: str
    description: str = ""
    inputs: list[ContractInput] = Field(default_factory=list)
    outputs: list[ContractOutput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> Contract:
        for what, items in (("input", self.inputs), ("output", self.outputs)):
            names = [i.name for i in items]
            dup = sorted({n for n in names if names.count(n) > 1})
            if dup:
                raise ValueError(f"{what} name(s) used twice: {', '.join(dup)}")
            targets = [i.target_id for i in items] if what == "input" else []
            twice = sorted({t for t in targets if targets.count(t) > 1})
            if twice:
                raise ValueError("a factor can be one input only")
        return self
