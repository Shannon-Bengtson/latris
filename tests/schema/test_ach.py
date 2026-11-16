"""ACH schema: ratings and evidence-item weights."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.ach import ACHItemEntry, ACHItemSet, ACHRatingEntry, ACHRatingSet


def test_bounds():
    with pytest.raises(ValidationError):
        ACHRatingEntry(target_id="e", hypothesis="h", rating="maybe")
    with pytest.raises(ValidationError):
        ACHItemEntry(target_id="e", credibility="very high")
    assert ACHItemEntry(target_id="e").credibility == "medium"


def test_round_trip(tmp_path: Path):
    ratings = ACHRatingSet(entries=[ACHRatingEntry(target_id="e", hypothesis="h", rating="II",
                                                   rationale="Contradicts the timeline.", origin="ai-proposed")])
    items = ACHItemSet(entries=[ACHItemEntry(target_id="e", credibility="high", relevance="low", source_id="log")])
    for model, cls, name in ((ratings, ACHRatingSet, "r.yaml"), (items, ACHItemSet, "i.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
