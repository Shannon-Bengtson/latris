"""The single YAML chokepoint. All YAML reads and writes go through this module.

Guarantees:
- UTF-8 on disk (defeats the Windows cp1252 trap).
- LF line endings on disk (matches .gitattributes).
- Atomic writes via tmp-file + os.replace.
- Deterministic output: pydantic field order → YAML key order, no sorting beyond that.
- Byte-identical round-trip: dump → load → dump produces identical bytes.
"""

from __future__ import annotations

import copy
import io
import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Sequence
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


def _dump_text(data) -> str:
    buf = io.StringIO()
    _make_yaml().dump(data, buf)
    text = buf.getvalue()
    return text if text.endswith("\n") else text + "\n"


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (UTF-8, LF), creating parent dirs.

    The temp file gets a unique name next to ``path`` so two concurrent
    writers of the same file can't clobber or delete each other's temp file;
    the last ``os.replace`` wins whole, never a mix of the two.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:12]}.tmp")
    try:
        # newline="" prevents Python from translating \n → \r\n on Windows.
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        atomic_replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def rewrite_jsonl(records: Sequence[BaseModel], path: Path) -> None:
    """Atomically replace a JSONL file with ``records`` (one per line)."""
    atomic_write_text(
        path, "".join(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n" for r in records)
    )


def dump_model(model: BaseModel, path: Path) -> None:
    """Serialise a pydantic model to ``path`` atomically (see :func:`atomic_write_text`)."""
    atomic_write_text(path, _dump_text(_normalise_for_yaml(model.model_dump(mode="json"))))


def load_raw_text(text: str):
    """Parse YAML text as plain data (dicts/lists); ``{}`` for an empty document."""
    return _parse(text)


def load_raw(path: Path):
    """Read YAML from ``path`` as plain data (dicts/lists), without validation.

    For store-agnostic maintenance (e.g. removing every row that points at a
    deleted element) where the concrete pydantic class varies by file.
    """
    data = _make_yaml().load(path.read_text(encoding="utf-8"))
    return {} if data is None else data


def dump_raw(data, path: Path) -> None:
    """Write plain data loaded with :func:`load_raw` back to ``path`` atomically."""
    atomic_write_text(path, _dump_text(data))


def load_model(cls: type[T], path: Path) -> T:
    """Read YAML from ``path`` and validate it into an instance of ``cls``.

    Creates a fresh YAML parser per call to avoid thread-safety issues
    when uvicorn serves concurrent requests (ruamel.yaml's internal
    parser state is not safe to share across threads).

    Parsing is the expensive part (the pure-Python parser; validation is
    cheap), and one operation often reads the same file many times — a
    report render reads the conceptual model dozens of times — so parsed
    text is cached (see :func:`_parse`). Every call still validates a fresh
    copy: callers own what they get back. Text that isn't YAML raises ``ValueError`` naming the file,
    as :func:`load_model_from_string` does.
    """
    from ruamel.yaml.error import YAMLError

    text = path.read_text(encoding="utf-8")
    try:
        data = _parse(text)
    except YAMLError as exc:
        raise ValueError(f"{path.name}: not valid YAML: {' '.join(str(exc).split())}") from exc
    return cls.model_validate(data)


# Parsed YAML keyed on the text itself, so a hit is exactly what parsing would
# give — no reliance on file timestamps, which are too coarse to see two quick
# writes. Reading a file is cheap; parsing it is what costs.
_PARSE_CACHE_MAX = 128
_parse_cache: OrderedDict[str, object] = OrderedDict()
_parse_cache_lock = threading.Lock()


def _parse(text: str) -> object:
    """``text`` parsed (a deep copy, safe to mutate); ``{}`` for an empty document."""
    with _parse_cache_lock:
        if text in _parse_cache:
            _parse_cache.move_to_end(text)
            return copy.deepcopy(_parse_cache[text])
    data = _make_yaml().load(text)
    if data is None:
        data = {}
    with _parse_cache_lock:
        _parse_cache[text] = data
        while len(_parse_cache) > _PARSE_CACHE_MAX:
            _parse_cache.popitem(last=False)
    return copy.deepcopy(data)


def load_model_or_default(cls: type[T], path: Path) -> T:
    """:func:`load_model`, or a fresh ``cls()`` when the file doesn't exist yet."""
    return load_model(cls, path) if path.exists() else cls()


def load_model_from_string(cls: type[T], text: str) -> T:
    """Parse YAML from a string and validate into an instance of ``cls``.

    Used by lineage operations to parse ``git show`` output without
    writing to a temp file, and to read text a person supplies (a build spec): text that isn't valid YAML
    or JSON raises ``ValueError`` saying where, like any other invalid input.
    """
    from ruamel.yaml.error import YAMLError

    try:
        data = _parse(text)
    except YAMLError as exc:
        raise ValueError(f"not valid YAML or JSON: {' '.join(str(exc).split())}") from exc
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
