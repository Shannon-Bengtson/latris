"""Bow-tie schema: barriers and threat frequencies."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.bow_tie import BTBarrierEntry, BTBarrierSet, BTFrequencyEntry, BTFrequencySet


def test_barrier_defaults_and_bounds():
    b = BTBarrierEntry(target_id="b")
    assert b.status == "in_place" and b.pfd is None and b.barrier_type is None
    with pytest.raises(ValidationError):
        BTBarrierEntry(target_id="b", pfd=1.5)
    with pytest.raises(ValidationError):
        BTBarrierEntry(target_id="b", barrier_type="procedural")
    with pytest.raises(ValidationError):
        BTFrequencyEntry(target_id="t", frequency=-1)


def test_round_trip(tmp_path: Path):
    barriers = BTBarrierSet(entries=[BTBarrierEntry(
        target_id="b", barrier_type="active_hardware", status="degraded", owner="Maintenance lead", pfd=0.01,
        origin="data-derived", source_id="lopa2001", verification="human-verified",
    )])
    freqs = BTFrequencySet(entries=[BTFrequencyEntry(target_id="t", frequency=0.1, notes="per year")])
    for model, cls, name in ((barriers, BTBarrierSet, "b.yaml"), (freqs, BTFrequencySet, "f.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
