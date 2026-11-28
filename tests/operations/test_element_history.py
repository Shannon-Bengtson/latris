"""The per-element history snippet fed into element-scope AI prompts."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import element_history
from latris.operations import evidence as ev_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations.element_history import element_history_snippet
from latris.operations.init import init_project
from latris.repo import git


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Does price affect demand?")
    return root


def _entries(snippet: str) -> list[str]:
    return [ln for ln in snippet.splitlines() if ln.startswith("- ")]


def test_an_unknown_element_has_no_history(project) -> None:
    node_ops.add_node("Price", root=project)
    assert element_history_snippet("node_NOTINTHEMODEL", root=project) is None


def test_history_lists_the_elements_commits_newest_first_with_rationale(project) -> None:
    price, _ = node_ops.add_node("Price", root=project)
    ref_ops.add_reference("r1", "Retail prices", root=project)
    ref_ops.add_reference("r2", "Demand curves", root=project)
    ev_ops.add_evidence(price.id, "existence", "r1", root=project)
    ev_ops.add_evidence(price.id, "existence", "r2", root=project)
    ev_ops.remove_evidence(price.id, "existence", "r1", rationale="measured wholesale, not retail", root=project)

    snippet = element_history_snippet(price.id, root=project)
    assert snippet is not None
    assert snippet.startswith("## Recent history for this element\n")
    entries = _entries(snippet)
    assert len(entries) == 3  # the default: three most recent
    assert 'Detached evidence "r1"' in entries[0]
    assert 'Attached evidence "r2"' in entries[1]
    assert "  Rationale: measured wholesale, not retail" in snippet.splitlines()


def test_recent_commits_caps_the_entries(project) -> None:
    a, _ = node_ops.add_node("Price", root=project)
    b, _ = node_ops.add_node("Demand", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=project)
    for key in ("r1", "r2", "r3"):
        ref_ops.add_reference(key, key, root=project)
        ev_ops.add_evidence(edge.id, "existence", key, root=project)

    snippet = element_history_snippet(edge.id, recent_commits=1, root=project)
    assert snippet is not None
    assert len(_entries(snippet)) == 1
    assert 'Attached evidence "r3"' in snippet


def test_commits_that_do_not_mention_the_element_are_left_out(project) -> None:
    a, _ = node_ops.add_node("Price", root=project)
    node_ops.add_node("Unrelated", root=project)  # touches the same file, not this element
    snippet = element_history_snippet(a.id, root=project)
    assert snippet is not None
    assert _entries(snippet) == [snippet.splitlines()[1]]
    assert 'Added node "Price"' in snippet
    assert "Unrelated" not in snippet


def test_long_subjects_and_rationales_are_shortened(project) -> None:
    a, _ = node_ops.add_node("P" * 120, root=project)
    b, _ = node_ops.add_node("Demand", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=project)
    ref_ops.add_reference("r1", "Ref", root=project)
    ref_ops.add_reference("r2", "Ref", root=project)
    ev_ops.add_evidence(edge.id, "existence", "r1", root=project)
    ev_ops.add_evidence(edge.id, "existence", "r2", root=project)
    ev_ops.remove_evidence(edge.id, "existence", "r1", rationale="x" * 300, root=project)

    snippet = element_history_snippet(edge.id, root=project)
    assert snippet is not None
    rationale = next(ln for ln in snippet.splitlines() if ln.startswith("  Rationale: "))
    assert rationale.endswith("…")
    assert len(rationale.removeprefix("  Rationale: ")) == element_history._MAX_RATIONALE_CHARS

    added = element_history_snippet(edge.id, recent_commits=5, root=project)
    assert added is not None
    subject_line = next(ln for ln in _entries(added) if "Added edge" in ln)
    subject = subject_line.split(": ", 1)[1]
    assert subject.endswith("…")
    assert len(subject) == element_history._MAX_SUBJECT_CHARS


def test_the_word_budget_trims_the_tail_but_keeps_one_entry_per_line(project, monkeypatch) -> None:
    edge_id = "edge_FAKE"
    long_rationale = " ".join(["a"] * 100)  # 70 one-letter words survive the 140-char cut
    record = (
        "__COMMIT__\x00{sha}\x002026-05-09T10:00:00+00:00\x00Retyped {eid}\x00rationale: {r}\x00__END__\n"
    )
    log = "".join(record.format(sha=f"{i:040d}", eid=edge_id, r=long_rationale) for i in range(3))

    monkeypatch.setattr(element_history, "_files_for_element", lambda eid, paths: [paths.conceptual_yaml])

    class _Out:
        stdout = log

    monkeypatch.setattr(git, "run_git", lambda *a, **k: _Out())
    snippet = element_history_snippet(edge_id, root=project)

    assert snippet is not None
    assert len(snippet.split()) <= element_history._MAX_WORDS
    assert snippet.rstrip("\n").endswith("…")
    lines = snippet.splitlines()
    assert lines[0] == "## Recent history for this element"
    assert lines[1] == f"- 2026-05-09: Retyped {edge_id}"
    assert lines[2].startswith("  Rationale: a a")


def test_a_git_failure_yields_no_history(project, monkeypatch) -> None:
    a, _ = node_ops.add_node("Price", root=project)
    b, _ = node_ops.add_node("Demand", root=project)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=project)

    def boom(*args, **kwargs):
        raise git.GitError("git exploded")

    monkeypatch.setattr(git, "run_git", boom)
    assert element_history_snippet(edge.id, root=project) is None


def test_an_unreadable_file_is_skipped(project, monkeypatch) -> None:
    a, _ = node_ops.add_node("Price", root=project)
    real_read = Path.read_text

    def flaky(self, *args, **kwargs):
        if self.name.startswith("conceptual"):
            raise OSError("locked")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert element_history_snippet(a.id, root=project) is None


def test_extract_rationale_takes_the_first_rationale_line() -> None:
    body = "id: edge_1\nrationale: first reason\nrationale: second"
    assert element_history._extract_rationale(body) == "first reason"
    assert element_history._extract_rationale("id: edge_1") is None
    assert element_history._extract_rationale("") is None
