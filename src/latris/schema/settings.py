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

from pydantic import BaseModel, ConfigDict


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
    """Markov chain / MDP settings."""

    model_type: Literal["markov"] = "markov"
    cycle_length: float = 1.0
    num_cycles: int = 50
    discount_rate: float = 0.035
    half_cycle_correction: bool = True
    time_units: str = "years"


class BNSettings(_SettingsBase):
    """Discrete Bayesian Network inference settings."""

    model_type: Literal["bn"] = "bn"
    inference_algorithm: Literal["variable_elimination"] = "variable_elimination"
