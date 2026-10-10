"""Tests for report-config persistence (Communicate phase), per model type."""

from __future__ import annotations

from pathlib import Path

from latris.operations.report_config import (
    load_report_config,
    load_report_config_store,
    save_report_config,
)
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model
from latris.schema.report_config import ReportConfig, ReportConfigStore, ReportPreset


def test_load_returns_defaults_when_absent(empty_project_root: Path) -> None:
    config = load_report_config("cld", root=empty_project_root)
    assert config.model_type == "cld"
    assert config.selected_sections == []
    assert config.voice == "formal"
    assert config.depth == "standard"
    assert config.saved_presets == []


def test_save_and_reload_roundtrip(empty_project_root: Path) -> None:
    config = ReportConfig(
        model_type="cld",
        selected_sections=["foundation", "interp_answer"],
        section_order=["foundation", "interp_answer"],
        voice="conversational",
        depth="detailed",
        saved_presets=[
            ReportPreset(name="My pack", sections=["foundation"], voice="executive", depth="summary"),
        ],
    )
    _, sha = save_report_config(config, root=empty_project_root)
    assert sha  # a commit was created

    reloaded = load_report_config("cld", root=empty_project_root)
    assert reloaded == config


def test_configs_are_isolated_per_model_type(empty_project_root: Path) -> None:
    save_report_config(ReportConfig(model_type="cld", selected_sections=["nodes"]), root=empty_project_root)
    save_report_config(ReportConfig(model_type="dag", selected_sections=["edges"]), root=empty_project_root)

    cld = load_report_config("cld", root=empty_project_root)
    dag = load_report_config("dag", root=empty_project_root)
    assert cld.selected_sections == ["nodes"]
    assert dag.selected_sections == ["edges"]

    store = load_report_config_store(root=empty_project_root)
    assert {c.model_type for c in store.configs} == {"cld", "dag"}


def test_save_writes_versioned_file(empty_project_root: Path) -> None:
    save_report_config(ReportConfig(model_type="cld", selected_sections=["nodes"]), root=empty_project_root)
    paths = ProjectPaths(empty_project_root)
    assert paths.report_config_yaml.exists()
    assert paths.report_config_yaml == empty_project_root / "communicate" / "report_config.yaml"


def test_legacy_single_config_file_migrates(empty_project_root: Path) -> None:
    """A pre-per-formalism file (one ReportConfig at the root) loads as one entry."""
    paths = ProjectPaths(empty_project_root)
    paths.report_config_yaml.parent.mkdir(parents=True, exist_ok=True)
    # Write the legacy shape directly (no `configs` wrapper, untyped).
    legacy = ReportConfig(selected_sections=["foundation"], voice="executive")
    dump_model(legacy, paths.report_config_yaml)

    store = load_report_config_store(root=empty_project_root)
    assert len(store.configs) == 1
    assert store.configs[0].selected_sections == ["foundation"]
    assert store.configs[0].voice == "executive"
    assert isinstance(store, ReportConfigStore)
