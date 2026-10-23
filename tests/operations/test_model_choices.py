"""Tests for model-choice provenance operations (append-only ModelChoiceLog)."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations.init import init_project
from latris.operations.project import (
    add_model_choice,
    current_model_choices,
    load_foundation,
    retire_model_choice,
    revise_model_choice,
)
from latris.operations.provenance import load_model_choices


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "proj"
    init_project(root, statement="Does X cause Y?")
    monkeypatch.chdir(root)
    return root


def _selected(root: Path) -> list[str]:
    _paths, foundation = load_foundation(root)
    return list(foundation.selected_model_types or [])


def test_add_model_choice_selects_and_logs(project):
    root = project
    add_model_choice("cld", "Feedback loops are central to this question.", root=root)

    assert _selected(root) == ["cld"]
    log = load_model_choices(root=root)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.model_type_id == "cld"
    assert entry.action == "added"
    assert entry.rationale.startswith("Feedback loops")
    assert entry.origin == "human-direct"


def test_add_with_ai_origin(project):
    root = project
    add_model_choice("dag", "Recommended for causal inference.", origin="ai-proposed", root=root)
    entry = load_model_choices(root=root).entries[0]
    assert entry.origin == "ai-proposed"


def test_current_model_choices_returns_latest_rationale(project):
    root = project
    add_model_choice("cld", "first reason", root=root)
    revise_model_choice("cld", "refined reason", root=root)

    log = load_model_choices(root=root)
    assert len(log.entries) == 2  # append-only: add + revise
    assert log.entries[1].action == "revised"

    current = current_model_choices(root=root)
    assert set(current) == {"cld"}
    assert current["cld"].rationale == "refined reason"


def test_retire_deselects_but_keeps_history(project):
    root = project
    add_model_choice("cld", "because loops", root=root)
    retire_model_choice("cld", "switched to a DAG instead", root=root)

    assert _selected(root) == []
    log = load_model_choices(root=root)
    actions = [e.action for e in log.entries]
    assert actions == ["added", "removed"]  # history preserved
    # A retired type drops out of the current view.
    assert current_model_choices(root=root) == {}


def test_add_already_selected_revises(project):
    root = project
    add_model_choice("cld", "first", root=root)
    add_model_choice("cld", "second", root=root)  # already selected → revise

    assert _selected(root) == ["cld"]  # no duplicate
    log = load_model_choices(root=root)
    assert [e.action for e in log.entries] == ["added", "revised"]
    assert current_model_choices(root=root)["cld"].rationale == "second"


def test_co_selected_formalisms_each_have_rationale(project):
    root = project
    add_model_choice("cld", "loops", root=root)
    add_model_choice("dag", "acyclic causal inference", root=root)

    assert _selected(root) == ["cld", "dag"]
    current = current_model_choices(root=root)
    assert current["cld"].rationale == "loops"
    assert current["dag"].rationale == "acyclic causal inference"


def test_add_planned_type_rejected(project):
    root = project
    with pytest.raises(ValueError, match="stable"):
        add_model_choice("markov", "state transitions", root=root)
    # Nothing should have been selected or logged.
    assert _selected(root) == []
    assert load_model_choices(root=root).entries == []


def test_model_choice_log_round_trip(project):
    """Schema round-trips through YAML (schema-before-code)."""
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema.provenance import ModelChoiceLog

    root = project
    add_model_choice("fcm", "weighted influence map", root=root)
    path = ProjectPaths(root).model_choices_yaml
    reloaded = load_model(ModelChoiceLog, path)
    assert reloaded.entries[0].model_type_id == "fcm"


def test_markdown_report_renders_modelling_approach(project):
    """The captured rationale surfaces in the report's Modelling Approach section."""
    from latris.exporters.markdown import render as render_md
    from latris.repo.layout import ProjectPaths

    root = project
    add_model_choice("cld", "Feedback loops are central to this question.", root=root)
    md = render_md(ProjectPaths(root))
    assert "## Modelling Approach" in md
    assert "Feedback loops are central to this question." in md


def test_markdown_no_approach_section_without_choices(project):
    from latris.exporters.markdown import render as render_md
    from latris.repo.layout import ProjectPaths

    md = render_md(ProjectPaths(project))
    assert "## Modelling Approach" not in md
