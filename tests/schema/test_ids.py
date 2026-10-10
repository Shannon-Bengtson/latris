from __future__ import annotations

from datetime import UTC, datetime

import pytest

from latris.schema.ids import id_timestamp, new_id, parse_id, validate_id


def test_new_id_is_unique():
    ids = [new_id("node") for _ in range(1000)]
    assert len(set(ids)) == 1000


def test_new_id_timestamp_portion_is_non_decreasing():
    # ULIDs encode a millisecond timestamp in the first 10 Crockford chars,
    # then 16 chars of randomness. Within the same ms, the random tail is
    # independent across calls — so full-string sort isn't guaranteed. The
    # *timestamp* prefix is guaranteed non-decreasing for IDs generated in
    # forward time.
    ids = [new_id("node") for _ in range(100)]
    prefixes = [i.split("_", 1)[1][:10] for i in ids]
    assert prefixes == sorted(prefixes)


def test_new_id_prefix_matches_kind():
    assert new_id("edge").startswith("edge_")
    assert new_id("challenge").startswith("challenge_")


def test_parse_id_roundtrip():
    raw = new_id("node")
    kind, ulid_part = parse_id(raw)
    assert kind == "node"
    assert len(ulid_part) == 26


def test_parse_id_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown ID kind"):
        parse_id("bogus_01H00000000000000000000000")


def test_parse_id_rejects_missing_prefix():
    with pytest.raises(ValueError, match="missing kind prefix"):
        parse_id("01H00000000000000000000000")


def test_parse_id_rejects_bad_ulid():
    with pytest.raises(ValueError):
        parse_id("node_not-a-ulid")


def test_validate_id_asserts_kind():
    nid = new_id("node")
    assert validate_id(nid, kind="node") == nid
    with pytest.raises(ValueError, match="expected ID kind"):
        validate_id(nid, kind="edge")


def test_id_timestamp_returns_recent_utc_datetime():
    before = datetime.now(tz=UTC)
    nid = new_id("node")
    after = datetime.now(tz=UTC)
    ts = id_timestamp(nid)
    assert ts.tzinfo is not None
    # The ULID timestamp is millisecond-precision; allow a one-ms slop window.
    assert before.replace(microsecond=before.microsecond // 1000 * 1000) <= ts <= after


def test_id_timestamp_accepts_bare_ulid():
    nid = new_id("node")
    _, ulid_part = parse_id(nid)
    assert id_timestamp(ulid_part) == id_timestamp(nid)


def test_id_timestamp_rejects_invalid():
    with pytest.raises(ValueError):
        id_timestamp("node_not-a-ulid")
    with pytest.raises(ValueError):
        id_timestamp("short")
