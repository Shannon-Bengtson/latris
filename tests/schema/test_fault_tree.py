"""Fault tree schema: gates and basic-event probabilities."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.fault_tree import FTGateEntry, FTGateSet, FTProbabilityEntry, FTProbabilitySet


def test_gates_and_vote_k():
    assert FTGateEntry(target_id="n", gate="and").k is None
    assert FTGateEntry(target_id="n", gate="vote", k=2).k == 2
    with pytest.raises(ValidationError, match="needs k"):
        FTGateEntry(target_id="n", gate="vote")
    with pytest.raises(ValidationError, match="only a vote gate"):
        FTGateEntry(target_id="n", gate="or", k=2)
    with pytest.raises(ValidationError):
        FTGateEntry(target_id="n", gate="xor")


def test_probability_bounds():
    assert FTProbabilityEntry(target_id="n", probability=0.0).probability == 0.0
    for bad in (-0.1, 1.5):
        with pytest.raises(ValidationError):
            FTProbabilityEntry(target_id="n", probability=bad)


def test_round_trip(tmp_path: Path):
    gates = FTGateSet(entries=[FTGateEntry(target_id="a", gate="vote", k=2), FTGateEntry(target_id="b", gate="or")])
    probs = FTProbabilitySet(entries=[FTProbabilityEntry(
        target_id="c", probability=1e-4, origin="data-derived", source_id="oreda2015", notes="per year",
    )])
    for model, cls, name in ((gates, FTGateSet, "g.yaml"), (probs, FTProbabilitySet, "p.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
