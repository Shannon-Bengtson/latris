"""Tests for the YAML I/O chokepoint (repo/yaml_io.py).

Every piece of persistent state is read/written through this module.
These tests verify round-trip fidelity, atomic writes, JSONL handling,
and edge cases (empty files, blank lines, encoding).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from latris.repo.yaml_io import (
    _normalise_for_yaml,
    dump_jsonl_append,
    dump_model,
    iter_jsonl,
    load_model,
    load_model_from_string,
)

# ── Tiny models for testing ─────────────────────────────────────────


class SimpleModel(BaseModel):
    name: str = ""
    count: int = 0


class NestedModel(BaseModel):
    label: str = ""
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)


class DefaultsModel(BaseModel):
    """Model where every field has a default — loading an empty file should work."""

    items: list[str] = Field(default_factory=list)
    active: bool = True


# ── dump_model / load_model round-trip ──────────────────────────────


def test_round_trip_simple(tmp_path: Path) -> None:
    path = tmp_path / "simple.yaml"
    original = SimpleModel(name="hello", count=42)
    dump_model(original, path)
    loaded = load_model(SimpleModel, path)
    assert loaded.name == original.name
    assert loaded.count == original.count


def test_round_trip_nested(tmp_path: Path) -> None:
    path = tmp_path / "nested.yaml"
    original = NestedModel(label="test", tags=["a", "b"], meta={"k": "v"})
    dump_model(original, path)
    loaded = load_model(NestedModel, path)
    assert loaded.label == "test"
    assert loaded.tags == ["a", "b"]
    assert loaded.meta == {"k": "v"}


def test_round_trip_preserves_field_order(tmp_path: Path) -> None:
    """YAML keys should follow pydantic field declaration order, not alphabetical."""
    path = tmp_path / "order.yaml"
    dump_model(NestedModel(label="z", tags=["a"]), path)
    text = path.read_text(encoding="utf-8")
    label_pos = text.index("label")
    tags_pos = text.index("tags")
    meta_pos = text.index("meta")
    assert label_pos < tags_pos < meta_pos


def test_dump_writes_utf8_lf(tmp_path: Path) -> None:
    path = tmp_path / "encoding.yaml"
    dump_model(SimpleModel(name="caf\u00e9"), path)
    raw = path.read_bytes()
    assert b"caf\xc3\xa9" in raw  # UTF-8 encoding of é
    assert b"\r\n" not in raw  # no CRLF, even on Windows
    assert raw.endswith(b"\n")  # trailing newline


def test_dump_ends_with_newline(tmp_path: Path) -> None:
    path = tmp_path / "newline.yaml"
    dump_model(SimpleModel(), path)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")


# ── Atomic write ────────────────────────────────────────────────────


def test_atomic_write_no_tmp_left(tmp_path: Path) -> None:
    path = tmp_path / "atomic.yaml"
    dump_model(SimpleModel(name="ok"), path)
    assert path.exists()
    assert not path.with_suffix(".yaml.tmp").exists()


def test_dump_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "deep.yaml"
    dump_model(SimpleModel(name="deep"), path)
    assert path.exists()
    loaded = load_model(SimpleModel, path)
    assert loaded.name == "deep"


def test_dump_retries_transient_permission_error(tmp_path: Path, monkeypatch) -> None:
    """A transient WinError-5 lock on the destination should be retried, not raised.

    Simulates antivirus/indexer/OneDrive momentarily holding a handle on the
    file we just wrote — os.replace fails the first time, succeeds on retry.
    """
    import latris.repo.yaml_io as yaml_io

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(yaml_io.os, "replace", flaky_replace)
    monkeypatch.setattr(yaml_io.time, "sleep", lambda _s: None)  # no real delay

    path = tmp_path / "retry.yaml"
    dump_model(SimpleModel(name="resilient", count=9), path)

    assert calls["n"] == 2  # failed once, succeeded on retry
    assert load_model(SimpleModel, path).name == "resilient"
    assert not path.with_suffix(".yaml.tmp").exists()


def test_dump_raises_after_persistent_permission_error(tmp_path: Path, monkeypatch) -> None:
    """A lock that never clears should still surface as PermissionError."""
    import latris.repo.yaml_io as yaml_io

    def always_locked(src, dst):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(yaml_io.os, "replace", always_locked)
    monkeypatch.setattr(yaml_io.time, "sleep", lambda _s: None)

    path = tmp_path / "stuck.yaml"
    try:
        dump_model(SimpleModel(name="nope"), path)
        raised = False
    except PermissionError:
        raised = True
    assert raised


def test_atomic_replace_is_public_and_retries(tmp_path: Path, monkeypatch) -> None:
    """The shared helper is callable directly and retries transient locks."""
    import latris.repo.yaml_io as yaml_io
    from latris.repo.yaml_io import atomic_replace

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(yaml_io.os, "replace", flaky_replace)
    monkeypatch.setattr(yaml_io.time, "sleep", lambda _s: None)

    src = tmp_path / "src.txt"
    src.write_text("payload", encoding="utf-8")
    dst = tmp_path / "dst.txt"
    atomic_replace(src, dst)

    assert calls["n"] == 2
    assert dst.read_text(encoding="utf-8") == "payload"


def test_atomic_replace_is_the_only_raw_os_replace() -> None:
    """Guard: every atomic write routes through atomic_replace.

    Raw ``os.replace`` for file replacement must live ONLY in yaml_io.py
    (the chokepoint). Any other occurrence in the package bypasses the
    Windows file-lock retry — regression-guard the four sites we just fixed.
    """
    import latris

    pkg_root = Path(latris.__file__).parent
    offenders = []
    for py in pkg_root.rglob("*.py"):
        if py.name == "yaml_io.py":
            continue
        text = py.read_text(encoding="utf-8")
        if "os.replace(" in text:
            offenders.append(py.relative_to(pkg_root).as_posix())
    assert offenders == [], f"raw os.replace outside yaml_io.py: {offenders}"


# ── Empty / missing content ─────────────────────────────────────────


def test_load_empty_yaml_returns_defaults(tmp_path: Path) -> None:
    """An empty YAML file should produce a model with all defaults."""
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    loaded = load_model(DefaultsModel, path)
    assert loaded.items == []
    assert loaded.active is True


def test_load_model_from_string_valid() -> None:
    text = "name: world\ncount: 7\n"
    loaded = load_model_from_string(SimpleModel, text)
    assert loaded.name == "world"
    assert loaded.count == 7


def test_load_model_from_string_empty() -> None:
    loaded = load_model_from_string(DefaultsModel, "")
    assert loaded.items == []


# ── JSONL round-trip ────────────────────────────────────────────────


def test_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    dump_jsonl_append(SimpleModel(name="a", count=1), path)
    dump_jsonl_append(SimpleModel(name="b", count=2), path)
    records = list(iter_jsonl(SimpleModel, path))
    assert len(records) == 2
    assert records[0].name == "a"
    assert records[1].name == "b"
    assert records[1].count == 2


def test_iter_jsonl_nonexistent_file(tmp_path: Path) -> None:
    path = tmp_path / "nope.jsonl"
    assert list(iter_jsonl(SimpleModel, path)) == []


def test_iter_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "blanks.jsonl"
    path.write_text(
        '{"name": "a", "count": 1}\n\n  \n{"name": "b", "count": 2}\n',
        encoding="utf-8",
    )
    records = list(iter_jsonl(SimpleModel, path))
    assert len(records) == 2


def test_jsonl_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "dir" / "log.jsonl"
    dump_jsonl_append(SimpleModel(name="nested"), path)
    assert path.exists()
    records = list(iter_jsonl(SimpleModel, path))
    assert len(records) == 1


# ── _normalise_for_yaml ─────────────────────────────────────────────


def test_normalise_returns_plain_types() -> None:
    data = {"items": [{"key": "val"}], "count": 3, "flag": True}
    result = _normalise_for_yaml(data)
    assert type(result) is dict
    assert type(result["items"]) is list
    assert type(result["items"][0]) is dict
    assert result["count"] == 3
    assert result["flag"] is True


def test_normalise_passes_through_scalars() -> None:
    assert _normalise_for_yaml("hello") == "hello"
    assert _normalise_for_yaml(42) == 42
    assert _normalise_for_yaml(None) is None


# ── Byte-identical round-trip ───────────────────────────────────────


def test_dump_is_byte_identical_on_double_dump(tmp_path: Path) -> None:
    """dump → load → dump produces identical bytes."""
    path1 = tmp_path / "first.yaml"
    path2 = tmp_path / "second.yaml"
    model = NestedModel(label="test", tags=["x", "y"], meta={"a": "b"})
    dump_model(model, path1)
    reloaded = load_model(NestedModel, path1)
    dump_model(reloaded, path2)
    assert path1.read_bytes() == path2.read_bytes()
