"""Per-model-type settings — discriminated by model type.

Model-level settings (time horizon, solver choice, discount rate, etc.)
that apply to a whole view, not to individual elements.  Each model type
gets its own settings class with required fields and real validation.

These are schema shells for now — operations and storage will be added
when each model type becomes stable.  Stored at:
``views/settings/{model_type}-settings.yaml``
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _SettingsBase(_Base):
    """Shared provenance fields for model-level settings."""

    set_by: str | None = None
    rationale: str | None = None


class SDSettings(_SettingsBase):
    """System Dynamics simulation settings."""

    model_type: Literal["sd"] = "sd"
    initial_time: float = 0.0
    final_time: float = 100.0
    dt: float = 0.25
    saveper: float | None = None
    integration_method: Literal["euler", "rk2", "rk4", "adaptive"] = "rk4"
    time_units: str = "years"


class FCMSettings(_SettingsBase):
    """Fuzzy Cognitive Map inference settings."""

    model_type: Literal["fcm"] = "fcm"
    transfer_function: Literal["sigmoid", "tanh", "step"] = "sigmoid"
    lambda_steepness: float = 1.0
    convergence_threshold: float = 0.001
    max_iterations: int = 100


class MarkovSettings(_SettingsBase):
    """Markov cohort model settings (stored at ``views/parameters/markov-settings.yaml``).

    ``discount_rate`` applies to costs, ``outcome_discount_rate`` to outcomes (default: the same rate).
    ``wtp`` is the willingness to pay per unit of outcome (e.g. per QALY) used for net benefit.
    """

    model_type: Literal["markov"] = "markov"
    cycle_length: float = Field(default=1.0, gt=0)
    num_cycles: int = Field(default=50, ge=1, le=10_000)
    discount_rate: float = Field(default=0.035, ge=0, le=1)
    outcome_discount_rate: float | None = Field(default=None, ge=0, le=1)
    half_cycle_correction: bool = True
    time_units: Literal["days", "weeks", "months", "years"] = "years"
    wtp: float | None = Field(default=None, ge=0)
    cost_units: str | None = None
    outcome_units: str | None = None


class BNSettings(_SettingsBase):
    """Discrete Bayesian Network inference settings."""

    model_type: Literal["bn"] = "bn"
    inference_algorithm: Literal["variable_elimination"] = "variable_elimination"
