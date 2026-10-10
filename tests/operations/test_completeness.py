"""Operation-level tests for AI interrogation Phase 2c CompletenessGate.

Covers:
- Merge logic respects prior excluded / dismissed / added_to_model rows.
- Override creates a linked Exclusion + flips status.
- Subsequent gate runs do not re-propose excluded names.
- Blocking-mode error path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.adapters import MockAdapter
from latris.ai.adapters.base import ChatResult
from latris.ai.proposals import (
    CompletenessGateResult,
    MissingVariableProposal,
)
from latris.operations import completeness as ops
from latris.operations.init import init_project
from latris.operations.nodes import add_node


@pytest.fixture(autouse=True)
def _ai_mock_mode(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "demo"
    init_project(root, statement="What drives nutrient runoff?")
    add_node("Nutrient load", root=root)
    add_node("Algal bloom", root=root)
    return root


def _register_gate_response(entries: list[MissingVariableProposal], coverage: float = 0.0) -> None:
    """Stub the mock adapter with a CompletenessGateResult."""
    result = CompletenessGateResult(
        coverage_ratio=coverage,
        entries=entries,
        model_type="cld",
    )
    MockAdapter.shared().register_default(
        response_cls=CompletenessGateResult,
        result=ChatResult(parsed=result, raw="(mock gate)", model_id="mock"),
    )


# ── Merge logic ─────────────────────────────────────────────────────────


def test_first_run_creates_open_entries(project: Path) -> None:
    _register_gate_response([
        MissingVariableProposal(
            name="Rainfall",
            rationale="Drives nutrient washout.",
            required_for=["Sensitivity claim"],
            severity="required",
            confidence="high",
        ),
    ])
    report, _ = ops.run_completeness_gate("cld", root=project)
    assert len(report.entries) == 1
    assert report.entries[0].disposition == "open"
    assert report.entries[0].name == "Rainfall"


def test_subsequent_run_dedupes_by_name(project: Path) -> None:
    """Re-running the gate must update existing open rows, not duplicate them."""
    proposal = MissingVariableProposal(
        name="Rainfall",
        rationale="First-pass rationale.",
        required_for=[],
        severity="recommended",
        confidence="medium",
    )
    _register_gate_response([proposal])
    ops.run_completeness_gate("cld", root=project)

    # Re-run with refined rationale + severity.
    refined = MissingVariableProposal(
        name="Rainfall",
        rationale="Refined: required for nutrient-load attribution.",
        required_for=["Sensitivity claim 2"],
        severity="required",
        confidence="high",
    )
    _register_gate_response([refined])
    report, _ = ops.run_completeness_gate("cld", root=project)
    assert len(report.entries) == 1
    mv = report.entries[0]
    assert mv.severity == "required"
    assert mv.confidence == "high"
    assert "Refined" in mv.rationale


def test_excluded_rows_never_reproposed(project: Path) -> None:
    _register_gate_response([
        MissingVariableProposal(
            name="Rainfall",
            rationale="Original.",
            required_for=[],
            severity="required",
            confidence="high",
        ),
    ])
    report, _ = ops.run_completeness_gate("cld", root=project)
    rainfall_id = report.entries[0].id

    ops.override_missing_variable(
        "cld",
        rainfall_id,
        rationale="Out of scope: not measuring weather in this study.",
        root=project,
    )

    # Re-run with the same proposal — must not re-add Rainfall.
    _register_gate_response([
        MissingVariableProposal(
            name="Rainfall",
            rationale="Trying to come back.",
            required_for=[],
            severity="required",
            confidence="high",
        ),
        MissingVariableProposal(
            name="Land cover",
            rationale="New variable.",
            required_for=[],
            severity="recommended",
            confidence="medium",
        ),
    ])
    report_after, _ = ops.run_completeness_gate("cld", root=project)
    names = [mv.name for mv in report_after.entries]
    assert "Rainfall" in names  # still present, but
    rainfall = next(mv for mv in report_after.entries if mv.name == "Rainfall")
    assert rainfall.disposition == "excluded"
    # Land cover IS a new open entry.
    land = next(mv for mv in report_after.entries if mv.name == "Land cover")
    assert land.disposition == "open"


def test_proposal_matching_existing_entity_label_is_dropped(project: Path) -> None:
    _register_gate_response([
        MissingVariableProposal(
            name="Nutrient load",  # already exists as an entity label
            rationale="Should not be proposed.",
            required_for=[],
            severity="required",
            confidence="high",
        ),
    ])
    report, _ = ops.run_completeness_gate("cld", root=project)
    assert report.entries == []


# ── Override → Exclusion flow ───────────────────────────────────────────


def test_override_creates_linked_exclusion(project: Path) -> None:
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema import ExclusionLog

    _register_gate_response([
        MissingVariableProposal(
            name="Rainfall",
            rationale="Original.",
            required_for=[],
            severity="required",
            confidence="high",
        ),
    ])
    report, _ = ops.run_completeness_gate("cld", root=project)
    mv_id = report.entries[0].id

    mv, sha = ops.override_missing_variable(
        "cld",
        mv_id,
        rationale="Out of scope for this study.",
        root=project,
    )
    assert sha
    assert mv.disposition == "excluded"
    assert mv.excluded_via_id is not None

    log = load_model(ExclusionLog, ProjectPaths(project).exclusions_yaml)
    matching = [e for e in log.entries if e.id == mv.excluded_via_id]
    assert len(matching) == 1
    assert "Rainfall" in matching[0].statement
    assert "Out of scope" in matching[0].rationale


def test_override_idempotent(project: Path) -> None:
    _register_gate_response([
        MissingVariableProposal(
            name="Rainfall",
            rationale="r",
            required_for=[],
            severity="required",
            confidence="medium",
        ),
    ])
    report, _ = ops.run_completeness_gate("cld", root=project)
    mv_id = report.entries[0].id

    ops.override_missing_variable("cld", mv_id, rationale="A", root=project)
    mv, sha = ops.override_missing_variable("cld", mv_id, rationale="B", root=project)
    # Second call returns the existing excluded row without producing a new commit.
    assert mv.disposition == "excluded"
    assert sha == ""


# ── State transitions ──────────────────────────────────────────────────


def test_dismiss_flips_disposition(project: Path) -> None:
    _register_gate_response([
        MissingVariableProposal(
            name="Wind",
            rationale="Maybe.",
            required_for=[],
            severity="optional",
            confidence="low",
        ),
    ])
    report, _ = ops.run_completeness_gate("cld", root=project)
    mv_id = report.entries[0].id
    mv, _ = ops.dismiss_missing_variable("cld", mv_id, root=project)
    assert mv.disposition == "dismissed"


def test_mark_added_records_entity(project: Path) -> None:
    _register_gate_response([
        MissingVariableProposal(
            name="Land cover",
            rationale="Yes.",
            required_for=[],
            severity="required",
            confidence="high",
        ),
    ])
    report, _ = ops.run_completeness_gate("cld", root=project)
    mv_id = report.entries[0].id
    mv, _ = ops.mark_added_to_model("cld", mv_id, "node_LANDCOVER", root=project)
    assert mv.disposition == "added_to_model"
    assert mv.added_entity_id == "node_LANDCOVER"


def test_unknown_id_raises(project: Path) -> None:
    with pytest.raises(ValueError, match="no missing-variable"):
        ops.dismiss_missing_variable("cld", "missing-var_DOES_NOT_EXIST", root=project)
