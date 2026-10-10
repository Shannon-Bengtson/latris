"""The ID chokepoint — every entity ID is a ULID with a kind prefix.

IDs look like ``<kind>_<ulid>`` (e.g. ``node_01J…``). The ULID carries a
millisecond timestamp, so ``id_timestamp`` recovers creation time without a
separate field. ``IDKind`` is the single source of truth for valid kinds;
``_ALL_KINDS`` is derived from it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, get_args

from ulid import ULID

IDKind = Literal[
    "node",
    "edge",
    "mapping",
    "view",
    "challenge",
    "assumption",
    "decision",
    "signoff",
    "session",
    "question",
    "exclusion",
    "prediction",
    "interaction",
    "elicitation",
    "dataset",
    "analysis-run",
    "finding",
    "version",
    "milestone",
    "data-action",
    "data-version",
    "reference",
    "interpret-section",
    "review-session",
    "missing-var",
    "story",
    "story-beat",
    "story-asset",
]

# Derived from the Literal so a new IDKind can never be added to the type
# but forgotten here (mirrors substrate._ENTITY_KINDS).
_ALL_KINDS: tuple[IDKind, ...] = get_args(IDKind)


def new_id(kind: IDKind) -> str:
    """Generate a new stable ID of the given kind.

    Format: ``<kind>_<ULID>``. The ULID suffix is 26 Crockford-base32 chars,
    time-sortable, and collision-safe for practical purposes.
    """
    return f"{kind}_{ULID()}"


def parse_id(value: str) -> tuple[IDKind, str]:
    """Split an ID into (kind, ulid). Raises ValueError if malformed."""
    if "_" not in value:
        raise ValueError(f"ID missing kind prefix: {value!r}")
    kind, _, ulid_part = value.partition("_")
    if kind not in _ALL_KINDS:
        raise ValueError(f"Unknown ID kind {kind!r} in {value!r}")
    if len(ulid_part) != 26:
        raise ValueError(f"ULID part must be 26 chars, got {len(ulid_part)} in {value!r}")
    try:
        ULID.from_str(ulid_part)
    except ValueError as exc:
        raise ValueError(f"Invalid ULID in {value!r}: {exc}") from exc
    return kind, ulid_part  # type: ignore[return-value]


def validate_id(value: str, *, kind: IDKind | None = None) -> str:
    """Validate an ID string, optionally asserting its kind. Returns the ID unchanged."""
    got_kind, _ = parse_id(value)
    if kind is not None and got_kind != kind:
        raise ValueError(f"expected ID kind {kind!r}, got {got_kind!r} ({value!r})")
    return value


def id_timestamp(value: str) -> datetime:
    """Extract the creation timestamp from a ULID-based ID.

    Accepts either a prefixed ID (``node_01H...``) or a bare 26-char ULID.
    ULIDs encode their generation time at millisecond precision, so this
    is the canonical replacement for redundant ``created_at`` fields.
    """
    if "_" in value:
        _, ulid_part = parse_id(value)
    else:
        ulid_part = value
        if len(ulid_part) != 26:
            raise ValueError(f"ULID part must be 26 chars, got {len(ulid_part)} in {value!r}")
    return ULID.from_str(ulid_part).datetime
