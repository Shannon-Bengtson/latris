"""Tests for shared attribute upsert helper.

The maturity-advancement helper was removed when maturity moved off
attribute entries onto the parent Entity/Edge — see
``operations/maturity.py`` and docs/design/MATURITY_LADDER.md.
"""

from dataclasses import dataclass, field

from latris.operations._attribute_helpers import upsert_entry


@dataclass
class _Entry:
    target_id: str
    attribute: str
    value: str


@dataclass
class _Store:
    entries: list[_Entry] = field(default_factory=list)


def _make_entry(target_id: str, value: str) -> _Entry:
    return _Entry(target_id=target_id, attribute="desc", value=value)


# -- upsert_entry -----------------------------------------------------------


def test_upsert_inserts_new_entry():
    store = _Store()
    upsert_entry(store, "ent_1", "desc", "hello", _make_entry)
    assert len(store.entries) == 1
    assert store.entries[0].value == "hello"


def test_upsert_updates_existing_entry():
    store = _Store(entries=[_Entry(target_id="ent_1", attribute="desc", value="old")])
    upsert_entry(store, "ent_1", "desc", "new", _make_entry)
    assert len(store.entries) == 1
    assert store.entries[0].value == "new"


def test_upsert_does_not_affect_other_entries():
    store = _Store(entries=[_Entry(target_id="ent_2", attribute="desc", value="keep")])
    upsert_entry(store, "ent_1", "desc", "added", _make_entry)
    assert len(store.entries) == 2
    assert store.entries[0].value == "keep"


# -- preserve_existing (non-destructive) + outcomes -------------------------


def test_upsert_returns_written_on_insert_and_overwrite():
    store = _Store()
    assert upsert_entry(store, "ent_1", "desc", "hello", _make_entry) == "written"
    assert upsert_entry(store, "ent_1", "desc", "changed", _make_entry) == "written"
    assert store.entries[0].value == "changed"


def test_preserve_existing_keeps_same_value():
    store = _Store(entries=[_Entry(target_id="ent_1", attribute="desc", value="v")])
    outcome = upsert_entry(store, "ent_1", "desc", "v", _make_entry, preserve_existing=True)
    assert outcome == "kept"
    assert store.entries[0].value == "v"


def test_preserve_existing_reports_conflict_without_overwriting():
    store = _Store(entries=[_Entry(target_id="ent_1", attribute="desc", value="old")])
    outcome = upsert_entry(store, "ent_1", "desc", "new", _make_entry, preserve_existing=True)
    assert outcome == "conflict"
    assert store.entries[0].value == "old"  # NOT overwritten


def test_preserve_existing_still_inserts_when_absent():
    store = _Store()
    outcome = upsert_entry(store, "ent_1", "desc", "hello", _make_entry, preserve_existing=True)
    assert outcome == "written"
    assert store.entries[0].value == "hello"
