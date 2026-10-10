"""Round-trip tests for the AI interrogation Phase 2c completeness schema."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from latris.repo.yaml_io import dump_model, load_model
from latris.schema import CompletenessReport, MissingVariable

FIXED_DT = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)


def test_round_trip_empty_report(tmp_path: Path) -> None:
    report = CompletenessReport(model_type="cld", generated_at=FIXED_DT)
    path = tmp_path / "report.yaml"
    dump_model(report, path)
    loaded = load_model(CompletenessReport, path)
    assert loaded == report


def test_round_trip_populated_report(tmp_path: Path) -> None:
    report = CompletenessReport(
        model_type="dag",
        generated_at=FIXED_DT,
        coverage_ratio=0.42,
        entries=[
            MissingVariable(
                id="missing-var_01EXAMPLE",
                name="Rainfall",
                rationale="Required to estimate nutrient washout.",
                required_for=["Algal bloom answers", "Sensitivity claim 3"],
                severity="required",
                confidence="high",
                detected_at=FIXED_DT,
            ),
            MissingVariable(
                id="missing-var_02EXAMPLE",
                name="Land use change",
                rationale="Long-run driver.",
                required_for=[],
                severity="recommended",
                confidence="medium",
                detected_at=FIXED_DT,
                disposition="excluded",
                excluded_via_id="exclusion_01ABC",
            ),
            MissingVariable(
                id="missing-var_03EXAMPLE",
                name="Irrigation",
                rationale="Mediator.",
                required_for=[],
                severity="optional",
                confidence="low",
                detected_at=FIXED_DT,
                disposition="added_to_model",
                added_entity_id="node_99XYZ",
            ),
        ],
    )
    path = tmp_path / "report.yaml"
    dump_model(report, path)
    bytes_first = path.read_bytes()
    loaded = load_model(CompletenessReport, path)
    assert loaded == report
    # Byte-identical round trip — clean git diffs.
    other = tmp_path / "report.2.yaml"
    dump_model(loaded, other)
    assert other.read_bytes() == bytes_first
