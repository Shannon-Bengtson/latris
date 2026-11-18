"""Shared storage for the formalism operations (operations/_view_store.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import fault_tree as ft
from latris.operations import nodes as node_ops
from latris.operations._view_store import ViewStore, replace_entry, resolve_factor
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.schema.fault_tree import FTProbabilityEntry, FTProbabilitySet
from latris.schema.mcda import MCDAScoreEntry, MCDAScoreSet


def test_replace_entry_by_target_and_by_compound_key() -> None:
    store = FTProbabilitySet()
    replace_entry(store, FTProbabilityEntry(target_id="a", probability=0.1))
    replace_entry(store, FTProbabilityEntry(target_id="b", probability=0.2))
    replace_entry(store, FTProbabilityEntry(target_id="a", probability=0.3))
    assert [(e.target_id, e.probability) for e in store.entries] == [("b", 0.2), ("a", 0.3)]

    scores = MCDAScoreSet()
    replace_entry(scores, MCDAScoreEntry(target_id="o", criterion="c1", value=1), "target_id", "criterion")
    replace_entry(scores, MCDAScoreEntry(target_id="o", criterion="c2", value=2), "target_id", "criterion")
    replace_entry(scores, MCDAScoreEntry(target_id="o", criterion="c1", value=3), "target_id", "criterion")
    assert sorted((e.criterion, e.value) for e in scores.entries) == [("c1", 3), ("c2", 2)]


def test_store_round_trip_roles_and_factor(empty_project_root: Path) -> None:
    root = empty_project_root
    paths = require_project(root)
    store = ViewStore("fault_tree", ("basic_event",))
    assert store.load(root, "probability", FTProbabilitySet).entries == []  # no file yet

    node_ops.add_node("Pump fails", root=root)
    node_ops.add_node("Line dry", root=root)
    edge_ops.add_edge("Pump fails", "Line dry", root=root)
    ft.set_event("Pump fails", "basic_event", root=root)
    ft.set_event("Line dry", "top_event", root=root)
    tid, label = resolve_factor(paths, "Pump fails", link_error="nope")
    assert label == "Pump fails"
    assert store.roles(root) == {tid: "basic_event"}  # top_event isn't in this store's elements

    s = FTProbabilitySet(entries=[FTProbabilityEntry(target_id=tid, probability=0.5)])
    sha = store.save(paths, "probability", s, subject="t")
    assert len(sha) == 40
    assert store.load(ProjectPaths(root), "probability", FTProbabilitySet) == s

    edge_id = edge_ops.list_edges(root)[0].id
    with pytest.raises(ValueError, match="is a link"):
        resolve_factor(paths, edge_id, link_error=f"{edge_id!r} is a link")


def test_is_weak() -> None:
    assert FTProbabilityEntry(target_id="a", probability=0.1).is_weak
    assert not FTProbabilityEntry(target_id="a", probability=0.1, verification="human-verified").is_weak
    assert FTProbabilityEntry(target_id="a", probability=0.1, verification="human-verified", contested=True).is_weak
