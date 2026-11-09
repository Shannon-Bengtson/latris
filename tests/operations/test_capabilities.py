"""Tests for the capability manifest (operations/capabilities.py)."""

from __future__ import annotations

from latris.operations.capabilities import build_capability_manifest


def test_manifest_counts_match_registry():
    manifest = build_capability_manifest()
    stable = [m for m in manifest["model_types"] if m["can_use_today"]]
    planned = [m for m in manifest["model_types"] if not m["can_use_today"]]
    assert {m["id"] for m in stable} == {"cld", "dag", "bn", "fcm", "sd"}
    assert len(planned) == 15
    assert manifest["excluded_by_design"]  # non-empty, hand-coded list present


def test_theory_of_change_marked_not_usable_today():
    manifest = build_capability_manifest()
    toc = next(m for m in manifest["model_types"] if m["id"] == "theory_of_change")
    assert toc["availability"] == "planned"
    assert toc["can_use_today"] is False


def test_manifest_roadmap_groups_and_order():
    manifest = build_capability_manifest()
    groups: dict[str, set[str]] = {}
    for m in manifest["model_types"]:
        groups.setdefault(m["roadmap"], set()).add(m["id"])
        assert (m["roadmap"] == "built") == m["can_use_today"]
    assert groups["built"] == {"cld", "dag", "fcm", "bn", "sd"}
    assert groups["roadmap"] == {"fault_tree", "event_tree", "bow_tie", "gsn", "theory_of_change"}
    assert groups["parked"] == {"decision_tree", "influence_diagram", "markov"}
    assert groups["not_planned"] == {
        "causal_dag", "regression", "argument_map", "fishbone", "flowchart", "state_machine", "petri_net",
    }
    order = [m["roadmap"] for m in manifest["model_types"]]
    rank = {"built": 0, "roadmap": 1, "parked": 2, "not_planned": 3}
    assert order == sorted(order, key=rank.__getitem__)


def test_manifest_carries_the_foundations_registry():
    manifest = build_capability_manifest()
    foundations = manifest["foundations"]
    ids = [f["id"] for f in foundations]
    assert len(ids) == len(set(ids))
    assert "evidence-source-check" in ids
    assert "sd-loop-dominance" in ids
    entry = next(f for f in foundations if f["id"] == "sd-simulation")
    assert tuple(entry["applies_to"]) == ("sd",)
    assert entry["method"] and entry["citation"] and entry["used_for"] and entry["limits"]
