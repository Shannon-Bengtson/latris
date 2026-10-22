"""Tests for the capability manifest (operations/capabilities.py)."""

from __future__ import annotations

from latris.operations.capabilities import build_capability_manifest


def test_manifest_counts_match_registry():
    manifest = build_capability_manifest()
    stable = [m for m in manifest["model_types"] if m["can_use_today"]]
    planned = [m for m in manifest["model_types"] if not m["can_use_today"]]
    assert {m["id"] for m in stable} == {"cld", "dag", "bn", "fcm"}
    assert len(planned) == 16
    assert manifest["excluded_by_design"]  # non-empty, hand-coded list present


def test_theory_of_change_marked_not_usable_today():
    manifest = build_capability_manifest()
    toc = next(m for m in manifest["model_types"] if m["id"] == "theory_of_change")
    assert toc["availability"] == "planned"
    assert toc["can_use_today"] is False
