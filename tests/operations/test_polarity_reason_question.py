"""A link's sign changed under its written reason raises a question; editing or removing the reason answers it."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations.edges import add_edge
from latris.operations.nodes import add_node
from latris.operations.project import add_model_choice
from latris.operations.view_attributes import get_view_attributes, set_view_attribute
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema.provenance import QuestionLog


@pytest.fixture
def link(empty_project_root: Path) -> str:
    a, _ = add_node("Traffic", root=empty_project_root)
    b, _ = add_node("Emissions", root=empty_project_root)
    edge, _ = add_edge(a.id, b.id, root=empty_project_root)
    add_model_choice("cld", root=empty_project_root)
    return edge.id


def _questions(root: Path) -> list:
    path = require_project(root).questions_yaml
    return load_model(QuestionLog, path).entries if path.exists() else []


def _reason(root: Path, edge_id: str) -> str | None:
    store = get_view_attributes("cld", "polarity", root=root)
    return next(e.rationale for e in store.entries if e.target_id == edge_id)


def test_a_flip_under_a_reason_asks_whether_it_still_holds(empty_project_root: Path, link: str) -> None:
    set_view_attribute(link, "cld", "polarity", "+", rationale="More cars, more exhaust.", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "-", root=empty_project_root)
    [q] = _questions(empty_project_root)
    assert q.target_id == link and q.concerns == "polarity_reason" and q.disposition == "open"
    assert "from + to -" in q.question and "More cars, more exhaust." in q.question
    assert _reason(empty_project_root, link) == "More cars, more exhaust."  # kept until the person decides


def test_flipping_again_does_not_ask_twice(empty_project_root: Path, link: str) -> None:
    set_view_attribute(link, "cld", "polarity", "+", rationale="More cars, more exhaust.", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "-", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "+", root=empty_project_root)
    assert len(_questions(empty_project_root)) == 1


@pytest.mark.parametrize(
    ("reason", "kept", "resolution"),
    [
        ("Fewer cars as transit improves.", "Fewer cars as transit improves.", "rewritten"),
        ("   ", None, "removed"),
        ("More cars, more exhaust.", "More cars, more exhaust.", "kept"),
    ],
)
def test_editing_or_removing_the_reason_answers_it(
    empty_project_root: Path, link: str, reason: str, kept: str | None, resolution: str
) -> None:
    set_view_attribute(link, "cld", "polarity", "+", rationale="More cars, more exhaust.", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "-", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "-", rationale=reason, root=empty_project_root)
    [q] = _questions(empty_project_root)
    assert q.disposition == "resolved" and resolution in (q.resolution or "")
    assert _reason(empty_project_root, link) == kept


def test_a_new_sign_with_its_own_reason_asks_nothing(empty_project_root: Path, link: str) -> None:
    set_view_attribute(link, "cld", "polarity", "+", rationale="More cars, more exhaust.", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "-", rationale="Congestion charge.", root=empty_project_root)
    assert _questions(empty_project_root) == []


def test_no_reason_no_question(empty_project_root: Path, link: str) -> None:
    set_view_attribute(link, "cld", "polarity", "+", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "-", root=empty_project_root)
    assert _questions(empty_project_root) == []


def test_the_question_is_in_the_same_change_so_one_undo_takes_both(empty_project_root: Path, link: str) -> None:
    from latris.operations.history import undo

    set_view_attribute(link, "cld", "polarity", "+", rationale="More cars, more exhaust.", root=empty_project_root)
    set_view_attribute(link, "cld", "polarity", "-", root=empty_project_root)
    undo(root=empty_project_root)
    assert _questions(empty_project_root) == []
    store = get_view_attributes("cld", "polarity", root=empty_project_root)
    assert next(e.value for e in store.entries if e.target_id == link) == "+"
