"""Replication manifests: every shipped one validates, round-trips and agrees with its build spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations.build import load_spec
from latris.operations.replications import REPLICATIONS_DIR, list_replications
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.replication import Replication

FOLDERS = sorted(d for d in REPLICATIONS_DIR.iterdir() if d.is_dir())


def test_every_folder_is_a_replication() -> None:
    assert FOLDERS, "no replications ship"
    for d in FOLDERS:
        assert (d / "replication.yaml").is_file(), f"{d.name}: no replication.yaml"
        assert (d / "spec.json").is_file(), f"{d.name}: no spec.json"
    assert [r.id for r in list_replications()] == [d.name for d in FOLDERS]


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda d: d.name)
def test_round_trip(folder: Path, tmp_path: Path) -> None:
    rep = load_model(Replication, folder / "replication.yaml")
    out = tmp_path / "replication.yaml"
    dump_model(rep, out)
    assert load_model(Replication, out) == rep


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda d: d.name)
def test_agrees_with_its_spec(folder: Path) -> None:
    rep = load_model(Replication, folder / "replication.yaml")
    spec = load_spec((folder / "spec.json").read_text(encoding="utf-8"))
    assert rep.id == folder.name
    assert spec.model_type == rep.model_type
    ids = [c.id for c in rep.checks]
    assert len(ids) == len(set(ids)), "check ids repeat"
    for c in rep.checks:
        index = getattr(c.measure, "analysis", None)
        if index is not None:
            assert index < len(spec.analyses), f"{c.id} reads analysis {index}"
        if isinstance(c.expected, float) and c.measure.kind != "loop_count":  # a count is exact
            assert c.abs_tol > 0 or c.rel_tol > 0, f"{c.id}: a number needs a tolerance"
    assert rep.source.citation and all(c.where for c in rep.checks)


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        Replication.model_validate({
            "id": "x", "title": "x", "model_type": "bn", "question": "x", "summary": "x",
            "source": {"citation": "x"}, "checks": [], "extra": 1,
        })
