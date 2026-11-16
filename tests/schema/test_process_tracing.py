"""Process-tracing schema: priors and tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.process_tracing import PTPriorEntry, PTPriorSet, PTTestEntry, PTTestSet


def test_open_bounds():
    for bad in (0.0, 1.0):
        with pytest.raises(ValidationError):
            PTPriorEntry(target_id="e", prior=bad)
        with pytest.raises(ValidationError):
            PTTestEntry(target_id="e", name="t", p_if_true=bad, p_if_false=0.5)
    assert PTTestEntry(target_id="e", name="t", p_if_true=0.9, p_if_false=0.2).found is None


def test_round_trip(tmp_path: Path):
    priors = PTPriorSet(entries=[PTPriorEntry(target_id="e", prior=0.4, source_id="baseline-study")])
    tests = PTTestSet(entries=[PTTestEntry(target_id="e", name="attendance records", p_if_true=0.9, p_if_false=0.4,
                                           found=True, source_id="school-data", description="Attendance rose")])
    for model, cls, name in ((priors, PTPriorSet, "p.yaml"), (tests, PTTestSet, "t.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
