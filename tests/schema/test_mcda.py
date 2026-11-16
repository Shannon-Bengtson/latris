"""MCDA schema: criterion weights, directions and scales; scores."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.mcda import MCDACriterionEntry, MCDACriterionSet, MCDAScoreEntry, MCDAScoreSet


def test_criterion_rules():
    assert MCDACriterionEntry(target_id="c").weight is None
    with pytest.raises(ValidationError):
        MCDACriterionEntry(target_id="c", weight=0)
    with pytest.raises(ValidationError, match="both worst and best"):
        MCDACriterionEntry(target_id="c", worst=1)
    with pytest.raises(ValidationError, match="must differ"):
        MCDACriterionEntry(target_id="c", worst=1, best=1)
    with pytest.raises(ValidationError, match="best must be below worst"):
        MCDACriterionEntry(target_id="c", direction="lower", worst=1, best=5)
    assert MCDACriterionEntry(target_id="c", direction="lower", worst=5, best=1).best == 1


def test_round_trip(tmp_path: Path):
    crit = MCDACriterionSet(entries=[MCDACriterionEntry(target_id="c", weight=30, direction="lower", worst=100,
                                                        best=0, units="$k", source_id="workshop")])
    scores = MCDAScoreSet(entries=[MCDAScoreEntry(target_id="o", criterion="c", value=42.5, origin="data-derived")])
    for model, cls, name in ((crit, MCDACriterionSet, "c.yaml"), (scores, MCDAScoreSet, "s.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
