from __future__ import annotations

from pathlib import Path

from latris.repo.yaml_io import dump_model
from latris.schema import ProjectFoundation


def test_dump_is_atomic_no_tmp_leftover(tmp_path: Path) -> None:
    path = tmp_path / "project.yaml"
    model = ProjectFoundation(statement="Q?")
    dump_model(model, path)
    assert path.exists()
    # The .tmp sibling must be gone after a successful write.
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_dump_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "c" / "project.yaml"
    model = ProjectFoundation(statement="Choose X.")
    dump_model(model, path)
    assert path.exists()


def test_dump_overwrites_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "project.yaml"
    m1 = ProjectFoundation(statement="Q1")
    m2 = ProjectFoundation(statement="D1")
    dump_model(m1, path)
    first_bytes = path.read_bytes()
    dump_model(m2, path)
    second_bytes = path.read_bytes()
    assert first_bytes != second_bytes
    # Sanity: file is well-formed and the second payload won.
    assert b"D1" in second_bytes
