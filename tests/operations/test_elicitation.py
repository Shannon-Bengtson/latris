"""Elicitation sessions: start, rounds, aggregation, finalising (and provenance), lookup by id or prefix."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from latris.operations import elicitation as el
from latris.operations.attributes import set_attribute
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import ConfidenceSet, DescriptionSet

DAY = date(2026, 1, 2)


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="What drives demand?")
    return root


@pytest.fixture
def price(project: Path) -> str:
    return add_node("Price", root=project)[0].id


def _start(root: Path, targets: list[tuple[str, str]], **kw):
    return el.start_session("delphi", "Alice", ["Dr A", "Dr B"], targets, held_at=DAY, root=root, **kw)


def test_start_writes_the_session_and_the_index(project: Path, price: str) -> None:
    session, sha = _start(project, [(price, "confidence")])
    assert sha == git.head_sha(project)
    assert session.id.startswith("elicitation_") and session.phase != "finalised"
    assert session.facilitator.name == "Alice" and [e.name for e in session.experts] == ["Dr A", "Dr B"]
    assert [(t.target_id, t.attribute) for t in session.target_attributes] == [(price, "confidence")]
    (entry,) = el.list_sessions(root=project)
    assert entry.id == session.id and entry.file_path.endswith("elicitations/2026-01-02-delphi-confidence.yaml")
    assert el.get_session(session.id, root=project) == session


def test_start_without_targets_or_date(project: Path) -> None:
    session, _ = el.start_session("workshop", "Alice", [], [], root=project)
    assert session.held_at == date.today()
    (entry,) = el.list_sessions(root=project)
    assert entry.file_path.endswith("-workshop-session.yaml")


def test_a_bad_protocol_writes_nothing(project: Path) -> None:
    head = git.head_sha(project)
    with pytest.raises(ValueError, match="protocol|Input should be"):
        el.start_session("nominal-group", "Alice", [], [], root=project)
    assert el.list_sessions(root=project) == [] and git.head_sha(project) == head


def test_two_sessions_on_the_same_day_keep_their_own_files(project: Path, price: str) -> None:
    first, _ = _start(project, [(price, "confidence")])
    second, _ = _start(project, [(price, "confidence")])
    files = [e.file_path for e in el.list_sessions(root=project)]
    assert files[0].endswith("-delphi-confidence.yaml") and files[1].endswith("-delphi-confidence-2.yaml")
    assert el.get_session(first.id, root=project).id == first.id
    assert el.get_session(second.id, root=project).id == second.id


def test_rounds_and_aggregation(project: Path, price: str) -> None:
    session, _ = _start(project, [(price, "confidence")])
    s, _ = el.add_round(session.id, "Dr A", "high", rationale="price data", root=project)
    s, _ = el.add_round(session.id, "Someone else", "low", round_num=2, root=project)
    first, second = s.raw_responses
    assert (first.expert.name, first.round, first.raw_input, first.rationale) == ("Dr A", 1, "high", "price data")
    assert (second.expert, second.round) == (None, 2)  # not on the panel: recorded without an expert
    s, sha = el.aggregate_session(session.id, {"confidence": "medium"}, confidence_summary="split", root=project)
    assert sha == git.head_sha(project)
    reloaded = el.get_session(session.id, root=project)
    assert reloaded.aggregated_result == {"confidence": "medium"} and reloaded.confidence_summary == "split"
    assert len(reloaded.raw_responses) == 2


def test_finalise_marks_the_elicited_attributes(project: Path, price: str) -> None:
    other = add_node("Demand", root=project)[0].id
    set_attribute(price, "confidence", "high", root=project)
    set_attribute(price, "description", "What a unit costs", root=project)
    set_attribute(other, "confidence", "low", root=project)
    session, _ = _start(project, [(price, "confidence")])
    s, sha = el.finalise_session(session.id, root=project)
    assert s.phase == "finalised" and sha == git.head_sha(project)
    paths = require_project(project)
    conf = {e.target_id: e for e in load_model(ConfidenceSet, paths.confidence_yaml).entries}
    assert (conf[price].origin, conf[price].verification, conf[price].source_id) == (
        "human-elicited", "human-verified", session.id)
    assert conf[other].origin != "human-elicited"  # not a target
    (desc,) = load_model(DescriptionSet, paths.descriptions_yaml).entries
    assert desc.origin != "human-elicited"  # a target's other attribute is untouched

    with pytest.raises(ValueError, match="already finalised"):
        el.finalise_session(session.id, root=project)
    with pytest.raises(ValueError, match="finalised session"):
        el.add_round(session.id, "Dr A", "x", root=project)
    with pytest.raises(ValueError, match="finalised session"):
        el.aggregate_session(session.id, {}, root=project)


def test_lookup_by_id_prefix(project: Path, price: str) -> None:
    session, _ = _start(project, [(price, "confidence")])
    assert el.get_session(session.id[: len("elicitation_") + 4], root=project).id == session.id
    with pytest.raises(ValueError, match="not found"):
        el.get_session(session.id[: len("elicitation_") + 3], root=project)  # too short to be a prefix
    with pytest.raises(ValueError, match="not found"):
        el.get_session("elicitation_", root=project)
    with pytest.raises(ValueError, match="not found"):
        el.get_session("elicitation_NOPE", root=project)


def test_an_ambiguous_prefix_is_refused(project: Path, price: str, monkeypatch) -> None:
    ids = iter(["elicitation_01AAAA0000000000000000000A", "elicitation_01AAAA0000000000000000000B"])
    monkeypatch.setattr(el, "new_id", lambda _kind: next(ids))
    a, _ = _start(project, [(price, "confidence")])
    _start(project, [(price, "description")])
    with pytest.raises(ValueError, match="ambiguous"):
        el.get_session("elicitation_01AAAA", root=project)
    assert el.get_session(a.id, root=project).id == a.id  # the full id is never ambiguous
