"""Decision tree schema: branches, payoffs, chance uncertainties, settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.decision_tree import (
    DTBranchEntry,
    DTBranchSet,
    DTChanceEntry,
    DTChanceSet,
    DTPayoffEntry,
    DTPayoffSet,
    DTSettings,
)


def test_bounds():
    with pytest.raises(ValidationError):
        DTBranchEntry(target_id="e", probability=1.2)
    with pytest.raises(ValidationError):
        DTSettings(objective="optimise")
    assert DTBranchEntry(target_id="e").value == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_values_and_probabilities_must_be_finite(bad: float):
    with pytest.raises(ValidationError):
        DTPayoffEntry(target_id="t", value=bad)
    with pytest.raises(ValidationError):
        DTBranchEntry(target_id="e", value=bad)
    with pytest.raises(ValidationError):
        DTBranchEntry(target_id="e", probability=bad)


def test_round_trip(tmp_path: Path):
    models = [
        (DTBranchSet(entries=[DTBranchEntry(target_id="e", label="High", probability=0.3, value=-5,
                                            source_id="survey", origin="data-derived")]), DTBranchSet),
        (DTPayoffSet(entries=[DTPayoffEntry(target_id="t", value=120.5, notes="NPV")]), DTPayoffSet),
        (DTChanceSet(entries=[DTChanceEntry(target_id="c", uncertainty="Demand")]), DTChanceSet),
        (DTSettings(objective="minimise", units="$k"), DTSettings),
    ]
    for i, (model, cls) in enumerate(models):
        dump_model(model, tmp_path / f"{i}.yaml")
        assert load_model(cls, tmp_path / f"{i}.yaml") == model
