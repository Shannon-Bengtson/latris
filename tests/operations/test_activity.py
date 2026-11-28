"""Recent activity reads in names, not IDs."""

from __future__ import annotations

from pathlib import Path

from latris.operations import activity
from latris.operations.activity import readable_subject, recent_activity
from latris.operations.edges import add_edge
from latris.operations.maturity import mark_reviewed
from latris.operations.nodes import add_node

NODE = "node_01M87GP3N19PS42ABCDEFGHJKM"


def test_a_whole_id_becomes_its_name() -> None:
    assert readable_subject(f"Maturity → approved: {NODE}", {NODE: "“Traffic”"}) == "Maturity → approved: “Traffic”"


def test_a_cut_short_id_matches_by_prefix_and_loses_its_ellipsis() -> None:
    assert readable_subject(f"Maturity → approved: {NODE[:20]}…", {NODE: "“Traffic”"}) == "Maturity → approved: “Traffic”"
    assert readable_subject(f"Map {NODE[:20]} to dag", {NODE: "“Traffic”"}) == "Map “Traffic” to dag"


def test_an_id_that_names_nothing_becomes_its_kind() -> None:
    assert readable_subject(f"Map {NODE[:20]} to cld", {}) == "Map a factor to cld"
    assert readable_subject("Set preferred version: version_01M87GP57Z456NMY7SYY798GZ8", {}) == "Set preferred version: a version"
    assert readable_subject("Removed assumption_01M87GP57Z456NMY7SYY798GZ8", {}) == "Removed an assumption"


def test_an_ambiguous_prefix_is_not_guessed() -> None:
    names = {NODE: "“A”", NODE[:-1] + "N": "“B”"}
    assert readable_subject(f"Map {NODE[:20]} to cld", names) == "Map a factor to cld"


def test_words_that_only_look_like_ids_are_left_alone() -> None:
    subject = 'Added node "Our local change" (concept)'
    assert readable_subject(subject, {}) == subject
    assert readable_subject("Selected model type: decision_tree", {}) == "Selected model type: decision_tree"


def test_recent_activity_names_factors_and_links(empty_project_root: Path) -> None:
    a, _ = add_node("Traffic", root=empty_project_root)
    b, _ = add_node("Air quality", root=empty_project_root)
    edge, _ = add_edge(a.id, b.id, root=empty_project_root)
    mark_reviewed(edge.id, root=empty_project_root)
    subjects = [e["subject"] for e in recent_activity(empty_project_root, limit=5)]
    assert not any("node_" in s or "edge_" in s for s in subjects), subjects
    assert any("Traffic → Air quality" in s for s in subjects), subjects


def test_a_project_that_cannot_be_read_still_lists_activity(empty_project_root: Path, monkeypatch) -> None:
    a, _ = add_node("Traffic", root=empty_project_root)
    mark_reviewed(a.id, root=empty_project_root)
    monkeypatch.setattr(activity, "_names", lambda root: {})
    assert recent_activity(empty_project_root, limit=1)[0]["subject"].endswith("a factor")
