"""The single YAML chokepoint. All YAML reads and writes go through this module.

Guarantees:
- UTF-8 on disk (defeats the Windows cp1252 trap).
- LF line endings on disk (matches .gitattributes).
- Atomic writes via tmp-file + os.replace.
- Deterministic output: pydantic field order → YAML key order, no sorting beyond that.
- Byte-identical round-trip: dump → load → dump produces identical bytes.
"""

from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel
from ruamel.yaml import YAML

T = TypeVar("T", bound=BaseModel)


def _make_yaml() -> YAML:
    y = YAML(typ="safe", pure=True)
    y.default_flow_style = False
    y.allow_unicode = True
    y.indent(mapping=2, sequence=4, offset=2)
    # Don't sort keys — preserve pydantic field order.
    y.sort_base_mapping_type_on_output = False  # type: ignore[attr-defined]
    return y


# NOTE: ruamel.yaml's YAML instances are NOT thread-safe — their internal
# parser/scanner/composer/emitter maintain stateful buffers that corrupt
# under concurrent access (e.g. uvicorn's thread pool). Both reads (load_model)
# and writes (dump_model) therefore create a fresh instance per call rather
# than sharing one. The cost is negligible; the safety is not.


def atomic_replace(tmp: str | os.PathLike, path: str | os.PathLike) -> None:
    """``os.replace`` with retry/backoff for transient Windows file locks.

    On Windows, ``os.replace`` raises ``PermissionError`` (WinError 5/32) when
    another process momentarily holds a handle on the destination — most often
    antivirus, the search indexer, or cloud-sync (OneDrive) scanning a file we
    just wrote. The lock is fleeting, so a few short retries reliably clears it.
    This is most visible on write-heavy loops like compose's per-node adds.

    On POSIX this is a plain ``os.replace`` (the loop succeeds first try).

    The single chokepoint for atomic file replacement — every ``tmp + replace``
    write across the package routes through here so the retry lives in one place.
    """
    delays = (0.01, 0.03, 0.06, 0.12, 0.25)
    for i, delay in enumerate(delays):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Last attempt: fall through to a final try that surfaces the error.
            if i == len(delays) - 1:
                break
            time.sleep(delay)
    os.replace(tmp, path)


def _normalise_for_yaml(data):
    """Convert pydantic JSON-mode output into plain Python primitives for ruamel.

    `model.model_dump(mode="json")` already returns JSON-safe types (datetimes
    stringified, etc.), so this is a no-op except that it forces pure dicts/lists
    (no pydantic-specific subclasses).
    """
    if isinstance(data, dict):
        return {k: _normalise_for_yaml(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_normalise_for_yaml(v) for v in data]
    return data


def dump_model(model: BaseModel, path: Path) -> None:
    """Serialise a pydantic model to ``path`` atomically.

    Writes to ``<path>.tmp`` first, then ``os.replace`` — atomic on
    Windows / macOS / Linux.
    """
    payload = _normalise_for_yaml(model.model_dump(mode="json"))
    buf = io.StringIO()
    _make_yaml().dump(payload, buf)
    text = buf.getvalue()
    if not text.endswith("\n"):
        text += "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # newline="" prevents Python from translating \n → \r\n on Windows.
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    atomic_replace(tmp, path)


def load_model(cls: type[T], path: Path) -> T:
    """Read YAML from ``path`` and validate it into an instance of ``cls``.

    Creates a fresh YAML parser per call to avoid thread-safety issues
    when uvicorn serves concurrent requests (ruamel.yaml's internal
    parser state is not safe to share across threads).
    """
    return load_model_from_string(cls, path.read_text(encoding="utf-8"))


def load_model_from_string(cls: type[T], text: str) -> T:
    """Parse YAML from a string and validate into an instance of ``cls``.

    Used by lineage operations to parse ``git show`` output without
    writing to a temp file.
    """
    y = _make_yaml()
    data = y.load(text)
    if data is None:
        data = {}
    return cls.model_validate(data)


def dump_jsonl_append(record: BaseModel, path: Path) -> None:
    """Append a single pydantic record to a JSONL file (one record per line).

    No atomic guarantees — append-only files accept partial tails as a natural
    consequence of being append-only. UTF-8 and LF explicit.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(line + "\n")


def iter_jsonl(cls: type[T], path: Path):
    """Iterate validated records from a JSONL file."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            yield cls.model_validate_json(raw)
