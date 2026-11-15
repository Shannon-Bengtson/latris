"""Event tree schema: structure, conditional probabilities, initiator frequency."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.event_tree import (
    ETFrequencyEntry,
    ETFrequencySet,
    ETProbabilityEntry,
    ETProbabilitySet,
    ETSequence,
    ETStep,
    ETStructure,
)


def test_bounds():
    with pytest.raises(ValidationError):
        ETProbabilityEntry(target_id="h", p_yes=1.2)
    with pytest.raises(ValidationError):
        ETStep(heading="h", answer="maybe")
    with pytest.raises(ValidationError):
        ETFrequencyEntry(target_id="i", frequency=-0.1)


def test_round_trip(tmp_path: Path):
    structure = ETStructure(headings=["a", "b"], sequences=[
        ETSequence(path=[ETStep(heading="a", answer="yes")], end_state="safe"),
        ETSequence(path=[ETStep(heading="a", answer="no"), ETStep(heading="b", answer="yes")], end_state="fire"),
    ])
    probs = ETProbabilitySet(entries=[
        ETProbabilityEntry(target_id="b", p_yes=0.3, given=[ETStep(heading="a", answer="no")], source_id="x"),
    ])
    freq = ETFrequencySet(entries=[ETFrequencyEntry(target_id="i", frequency=0.02, origin="data-derived")])
    for model, cls, name in ((structure, ETStructure, "s.yaml"), (probs, ETProbabilitySet, "p.yaml"),
                             (freq, ETFrequencySet, "f.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
