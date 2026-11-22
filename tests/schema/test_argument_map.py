"""Argument map schema: links (supports or attacks, reason, warrant, qualifier) and claim assessments."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from latris.repo.yaml_io import dump_model, load_model
from latris.schema.argument_map import ArgumentClaimEntry, ArgumentClaimSet, ArgumentLinkEntry, ArgumentLinkSet


def test_bounds():
    with pytest.raises(ValidationError):
        ArgumentLinkEntry(target_id="e", relation="undermines")
    with pytest.raises(ValidationError):
        ArgumentLinkEntry(target_id="e", qualifier="definitely")
    with pytest.raises(ValidationError):
        ArgumentClaimEntry(target_id="c", assessment="maybe")
    assert ArgumentLinkEntry(target_id="e").relation == "supports"


def test_round_trip(tmp_path: Path):
    links = ArgumentLinkSet(entries=[
        ArgumentLinkEntry(target_id="e1", relation="supports", reason="affordable and effective",
                          warrant="A treatment that works and can be paid for should be funded.",
                          qualifier="probably", origin="ai-proposed"),
        ArgumentLinkEntry(target_id="e2", relation="attacks", source_id="audit"),
    ])
    claims = ArgumentClaimSet(entries=[ArgumentClaimEntry(target_id="c", assessment="accepted",
                                                          rationale="Agreed at the board.")])
    for model, cls, name in ((links, ArgumentLinkSet, "l.yaml"), (claims, ArgumentClaimSet, "c.yaml")):
        dump_model(model, tmp_path / name)
        assert load_model(cls, tmp_path / name) == model
