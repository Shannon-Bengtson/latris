"""Checkpoints: where an AI building a model asks the person (operations/checkpoints.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import checkpoints as cp
from latris.operations.edges import add_edge
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.operations.project import update_foundation
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import PersonInputLog


@pytest.fixture
def ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """New work is AI-proposed, as when an agent drives latris."""
    monkeypatch.setenv("LATRIS_DEFAULT_ORIGIN", "ai-proposed")


@pytest.fixture
def root(tmp_path: Path, git_identity) -> Path:
    r = tmp_path / "proj"
    init_project(r, statement="Why are volunteers leaving?")
    return r


def _map(root: Path, extra: tuple[str, ...] = ()) -> dict[str, str]:
    ids = {}
    for label in ("Workload", "Burnout", "Volunteers", "Recognition", *extra):
        ids[label] = add_node(label, kind="variable", root=root)[0].id
    add_edge(ids["Workload"], ids["Burnout"], kind="causal", root=root)
    add_edge(ids["Burnout"], ids["Volunteers"], kind="causal", root=root)
    add_edge(ids["Volunteers"], ids["Workload"], kind="causal", root=root)
    add_edge(ids["Recognition"], ids["Volunteers"], kind="causal", root=root)
    for label in extra:
        add_edge(ids[label], ids["Volunteers"], kind="causal", root=root)
    return ids


def _framed(root: Path) -> None:
    update_foundation({"background": "Numbers fell 30%.", "audience": "The board",
                       "predictions": "Burnout, mostly."}, root=root)


def _state(root: Path, cid: str) -> str:
    return next(s.state for s in cp.checkpoint_report(root=root).checkpoints if s.id == cid)


def test_framing_asks_only_whats_missing(root: Path, ai) -> None:
    update_foundation({"audience": "The board"}, root=root)
    c = cp.open_checkpoint(root=root)
    assert c is not None and c.id == "framing"
    assert len(c.questions) == 2
    assert any("decision" in q for q in c.questions)
    assert any("Why are volunteers leaving" in q for q in c.questions)  # the person's own question, named
    assert not any("read the result" in q for q in c.questions)


def test_framing_closes_when_context_is_on_record(root: Path, ai) -> None:
    _framed(root)
    assert _state(root, "framing") == "not_needed"
    assert cp.open_checkpoint(root=root) is None  # nothing built yet: structure not reached


def test_structure_names_factors_drivers_and_weakest_link(root: Path, ai) -> None:
    from latris.operations.view_roles import set_role

    _framed(root)
    _map(root)
    set_role("Volunteers", "cld", "outcome", root=root)
    c = cp.open_checkpoint(root=root)
    assert c is not None and c.id == "structure"
    assert "4 factors and 4 links around 'Volunteers'" in c.questions[0]
    assert "'Burnout' and 'Recognition' can you actually change" in c.questions[1]
    assert "→" in c.questions[2] and "no source yet" in c.questions[2]
    assert len(c.covers) == 4


def test_structure_waits_for_a_connected_map(root: Path, ai) -> None:
    _framed(root)
    add_node("Workload", kind="variable", root=root)
    add_node("Burnout", kind="variable", root=root)
    add_node("Volunteers", kind="variable", root=root)
    assert _state(root, "structure") == "not_reached"


def test_answer_closes_and_big_growth_reopens(root: Path, ai) -> None:
    _framed(root)
    _map(root)
    entry, sha = cp.record_input("structure", "Add travel costs. We control shift length.", root=root)
    assert sha and entry.outcome == "answered" and entry.questions  # the questions asked are kept
    assert _state(root, "structure") == "answered"
    ids = {e: add_node(e, kind="variable", root=root)[0].id for e in ("Travel", "Shifts", "Training")}
    vol = load_model(PersonInputLog, ProjectPaths(root).person_input_yaml).entries[0].covers
    assert len(vol) == 4
    for nid in ids.values():
        add_edge(nid, entry.covers[0], kind="causal", root=root)
    assert _state(root, "structure") == "open"  # 3 new factors on a map of 4: reviewed map is stale


def test_skip_is_recorded_with_reason(root: Path, ai) -> None:
    entry, _ = cp.skip_checkpoint("framing", "The person asked me to just build.", root=root)
    assert entry.outcome == "skipped" and entry.questions
    assert _state(root, "framing") == "skipped"
    with pytest.raises(ValueError, match="why"):
        cp.skip_checkpoint("framing", " ", root=root)


def test_just_build_pace_opens_nothing(root: Path, ai) -> None:
    cp.set_pace("just_build", root=root)
    report = cp.checkpoint_report(root=root)
    assert report.open is None and report.pace == "just_build"
    assert _state(root, "framing") == "not_asked"
    cp.set_pace("ask", root=root)
    assert cp.open_checkpoint(root=root) is not None


def test_human_built_models_get_no_checkpoints(root: Path) -> None:
    _map(root)  # origin human-direct
    report = cp.checkpoint_report(root=root)
    assert report.open is None
    assert {s.state for s in report.checkpoints} == {"not_needed"}


def test_surprise_and_audience_follow_a_result(root: Path, ai) -> None:
    from latris.operations.findings import record_new_finding

    _framed(root)
    _map(root)
    cp.record_input("structure", "Looks right.", root=root)
    assert _state(root, "surprise") == "not_reached"
    record_new_finding("Recognition matters more than workload.", "sensitivity", "cld", root=root)
    c = cp.open_checkpoint(root=root)
    assert c is not None and c.id == "surprise"
    assert "Burnout, mostly." in c.questions[0] and "Recognition matters more" in c.questions[0]
    cp.record_input("surprise", "That surprises me — recognition was cut last year.", root=root)
    c = cp.open_checkpoint(root=root)
    assert c is not None and c.id == "audience" and "'The board'" in c.questions[0]


def test_values_from_sensitivity_payloads() -> None:
    qs = cp._value_questions({
        "parameters": [
            {"label": "Burnout rate", "baseline_value": 0.15, "units": "1/month", "swing": 40, "weak": True},
            {"label": "Hours", "baseline_value": 3, "units": "", "swing": 30, "weak": False},  # checked: not asked
            {"label": "Off", "baseline_value": 1, "swing": 0, "weak": True},  # no effect: not asked
        ],
    })
    assert len(qs) == 1 and "'Burnout rate' is 0.15 1/month" in qs[0]
    qs = cp._value_questions({
        "labels": {"n_1": "Leaves", "n_2": "Burnout"},
        "findings": [{"node_id": "n_1", "state": "yes", "parent_states": {"n_2": "high"}, "baseline_prob": 0.4,
                      "influence": 0.2, "weak": True}],
    })
    assert qs == ["The chance of 'Leaves = yes' when Burnout = high is 40% — my estimate, and the answer is "
                  "among the most sensitive to it. Does that sound right?"]


def test_record_refuses_unknown_checkpoint_and_empty_answers(root: Path) -> None:
    with pytest.raises(ValueError, match="checkpoint must be"):
        cp.record_input("vibes", "x", root=root)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="answers"):
        cp.record_input("framing", "  ", root=root)


def test_relayed_by_names_the_agent(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LATRIS_RECORDED_BY_AGENT", "claude-code")
    entry, _ = cp.record_input("framing", "It's for the board.", root=root)
    assert entry.relayed_by == "claude-code"


def test_values_names_the_estimates_sensitivity_ranks_highest(sd_bathtub_root: Path) -> None:
    from latris.operations import sd as sd_ops
    from latris.repo.yaml_io import dump_model
    from latris.schema import Substrate

    root = sd_bathtub_root
    paths = ProjectPaths(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)  # as if an agent built it
    for e in substrate.entities:
        e.origin = "ai-proposed"
    dump_model(substrate, paths.conceptual_yaml)
    _framed(root)
    cp.record_input("structure", "Fine.", root=root)

    c = cp.open_checkpoint(root=root)
    assert c is not None and c.id == "values"
    assert c.before_asking and "sd_sensitivity" in c.before_asking  # no sensitivity run yet: run one first

    stock = next(e.label for e in substrate.entities if e.label == "Water")
    sd_ops.record_sensitivity(sd_ops.run_sensitivity(stock, root=root), root=root)
    c = cp.open_checkpoint(root=root)
    assert c is not None and c.id == "values" and c.before_asking is None
    assert c.questions and all("my estimate" in q for q in c.questions)
