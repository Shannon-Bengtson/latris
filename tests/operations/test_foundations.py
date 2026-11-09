"""Tests for the methods-and-foundations registry (operations/foundations.py)."""

from __future__ import annotations

from latris.operations.foundations import FOUNDATIONS, foundations_for_report
from latris.repo.project import require_project
from latris.schema.model_types import MODEL_TYPE_REGISTRY


def test_ids_are_unique():
    ids = [f.id for f in FOUNDATIONS]
    assert len(ids) == len(set(ids))


def test_applies_to_entries_are_registered_model_types_or_wildcard():
    for f in FOUNDATIONS:
        for mt in f.applies_to:
            assert mt == "*" or mt in MODEL_TYPE_REGISTRY, f"{f.id}: unknown model type {mt!r}"


def test_fields_are_non_empty():
    for f in FOUNDATIONS:
        assert f.id.strip()
        assert f.applies_to
        assert f.method.strip()
        assert f.citation.strip()
        assert f.used_for.strip()
        assert f.limits is None or f.limits.strip()


def test_registry_has_the_expected_shape():
    by_id = {f.id: f for f in FOUNDATIONS}
    assert set(by_id) >= {
        "cld-loop-analysis", "dag-identification", "bn-exact-inference", "bn-parameter-learning",
        "fcm-steady-state", "sd-simulation", "sd-uncertainty", "sd-sensitivity", "sd-loop-dominance",
        "evidence-source-check",
    }
    assert by_id["evidence-source-check"].applies_to == ("*",)


def test_empty_project_selects_nothing(empty_project_root):
    assert foundations_for_report(require_project(empty_project_root)) == []


def test_evidence_entry_included_when_references_exist(empty_project_root):
    from latris.operations import references as ref_ops

    ref_ops.add_reference("ster2000", "Business Dynamics",
                          authors=["Sterman, John"], year=2000, root=empty_project_root)
    selected = foundations_for_report(require_project(empty_project_root))
    assert [f.id for f in selected] == ["evidence-source-check"]
