"""Markov schema: transitions, rewards, start, settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.markov import (
    MarkovRewardEntry,
    MarkovRewardSet,
    MarkovStartEntry,
    MarkovStartSet,
    MarkovTransitionEntry,
    MarkovTransitionSet,
)
from latris.schema.settings import MarkovSettings


def test_bounds():
    with pytest.raises(ValidationError):
        MarkovTransitionEntry(target_id="e", probability=1.5)
    with pytest.raises(ValidationError):
        MarkovStartEntry(target_id="s", proportion=-0.1)
    with pytest.raises(ValidationError):
        MarkovSettings(time_units="fortnights")
    with pytest.raises(ValidationError):
        MarkovSettings(num_cycles=0)


def test_round_trip(tmp_path: Path):
    models = [
        (MarkovTransitionSet(entries=[MarkovTransitionEntry(target_id="e", strategy="drug", probability=0.05,
                                                            source_id="trial")]), MarkovTransitionSet),
        (MarkovRewardSet(entries=[MarkovRewardEntry(target_id="s", cost=1200, utility=0.7)]), MarkovRewardSet),
        (MarkovStartSet(entries=[MarkovStartEntry(target_id="s", proportion=1.0)]), MarkovStartSet),
        (MarkovSettings(num_cycles=40, wtp=20000, cost_units="£", outcome_units="QALY"), MarkovSettings),
    ]
    for i, (model, cls) in enumerate(models):
        dump_model(model, tmp_path / f"{i}.yaml")
        assert load_model(cls, tmp_path / f"{i}.yaml") == model
