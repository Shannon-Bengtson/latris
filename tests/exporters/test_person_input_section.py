"""The report's "What the person reviewed" section (exporters/markdown.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters.markdown import render
from latris.operations import checkpoints as cp
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.layout import ProjectPaths


def _project(root: Path) -> Path:
    init_project(root, statement="Why do volunteers leave?")
    ids = [add_node(x, kind="variable", root=root)[0].id for x in ("Workload", "Burnout", "Volunteers")]
    add_edge(ids[0], ids[1], kind="causal", root=root)
    add_edge(ids[1], ids[2], kind="causal", root=root)
    return root


def test_ai_built_report_says_what_was_asked(tmp_path: Path, git_identity, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LATRIS_DEFAULT_ORIGIN", "ai-proposed")
    root = _project(tmp_path / "p")
    cp.record_input("framing", "For the board. I expect burnout.", root=root)
    cp.skip_checkpoint("structure", "The person asked me to carry on.", root=root)
    md = render(ProjectPaths(root), pack="client", ai=False)
    assert "## What the person reviewed" in md
    assert "“For the board. I expect burnout.”" in md
    assert "not asked — The person asked me to carry on." in md
    assert "**Values — the estimates the answer depends on most:** not reached." in md


def test_person_built_report_has_no_such_section(tmp_path: Path, git_identity) -> None:
    root = _project(tmp_path / "p")
    md = render(ProjectPaths(root), pack="audit", ai=False)
    assert "What the person reviewed" not in md
