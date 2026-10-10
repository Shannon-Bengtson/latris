"""Pytest wrapper for the worked example — runs the full demo and asserts success.

This test regenerates worked_example/worked_example_output.md on every run.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _git_and_mock(monkeypatch: pytest.MonkeyPatch):
    """Set hermetic git identity and mock mode."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Demo Runner")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "demo@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Demo Runner")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "demo@example.invalid")
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")


@pytest.mark.slow
@pytest.mark.xdist_group("serial")
def test_worked_example_completes_without_failures():
    """The entire worked example runs, all commands exit 0, transcript is written."""
    from worked_example.worked_example import run_worked_example

    # Write transcript to the canonical location
    output_dir = Path(__file__).resolve().parent.parent / "worked_example"
    ex = run_worked_example(output_dir=output_dir)

    assert not ex.failures, f"{len(ex.failures)} command(s) failed:\n" + "\n".join(f"  - {f}" for f in ex.failures)

    transcript = output_dir / "worked_example_output.md"
    assert transcript.exists(), "Transcript was not written"

    content = transcript.read_text(encoding="utf-8")
    assert "## Project Setup" in content
    assert "## Building the Model" in content
    assert "## AI-Assisted Modelling" in content
    assert "## Export" in content
    assert "## History" in content
