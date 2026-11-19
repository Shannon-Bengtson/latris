"""Tests for readiness assessment operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.findings import record_new_finding
from latris.operations.init import init_project
from latris.operations.interpret import save_interpretation
from latris.operations.project import add_model_choice, update_selected_models
from latris.operations.readiness import (
    assess_all_readiness,
    assess_readiness,
    assess_transition_readiness,
)
from latris.schema.ids import new_id
from latris.schema.interpretation import InterpretationStore, InterpretSection


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    c, _ = node_ops.add_node("Quantity", kind="variable", root=root)
    e1, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    # Connect the third node so the graph is a single weakly-connected
    # network (passes the Build→Formalise gate). Acyclic, so DAG stays ready.
    edge_ops.add_edge(b.id, c.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, a, b, e1


def test_cld_readiness_requires_loops(project):
    """CLD requires at least one feedback loop — loops are the defining
    feature of the formalism, so an acyclic CLD is treated as incomplete.
    This blocks the silent-pass behaviour where AI-built CLDs lacking
    loops were marked ready."""
    root, _, _, _ = project
    # Project fixture has one edge A→B and no loop yet.
    r = assess_readiness("cld", root=root)
    assert r.score == 0
    assert r.can_switch is False
    assert any(g.gap_type == "no_loops" for g in r.gaps)


def test_cld_readiness_passes_with_loop(project):
    """Once a loop exists the CLD readiness clears."""
    root, a, b, _ = project
    edge_ops.add_edge(b.id, a.id, kind="causal", root=root)
    r = assess_readiness("cld", root=root)
    assert r.score == 100
    assert r.can_switch is True


def test_cld_readiness_ignores_decision_rule_loops(project):
    """Loops closed by non-causal edges (decision_rule, governance,
    flow, ...) don't satisfy the CLD readiness gate. The capability run
    inflated loop counts by treating decision rules as feedback
    mechanism — Phase 1 of the AI interrogation layer fixes that here."""
    root, a, b, _ = project
    # Close the loop with a decision_rule edge — should NOT count.
    edge_ops.add_edge(b.id, a.id, kind="decision_rule", root=root)
    r = assess_readiness("cld", root=root)
    assert r.score == 0
    assert r.can_switch is False
    assert any(g.gap_type == "no_loops" for g in r.gaps)


def test_dag_readiness_ignores_decision_rule_cycles(project):
    """Cycles formed by non-causal edges don't trip the DAG acyclicity
    gate — they aren't part of the causal mechanism the DAG models."""
    root, a, b, _ = project
    c, _ = node_ops.add_node("Revenue", kind="variable", root=root)
    # Causal edges form an acyclic chain a→b→c; governance edge c→a
    # closes a non-causal "cycle" that must be ignored.
    edge_ops.add_edge(b.id, c.id, kind="causal", root=root)
    edge_ops.add_edge(c.id, a.id, kind="governance", root=root)
    r = assess_readiness("dag", root=root)
    assert r.score == 100
    assert r.can_switch is True


def test_dag_readiness_acyclic(project):
    root, _, _, _ = project
    r = assess_readiness("dag", root=root)
    assert r.score == 100
    assert r.can_switch is True


def test_dag_readiness_with_cycle(project):
    root, a, b, _ = project
    c, _ = node_ops.add_node("Revenue", kind="variable", root=root)
    edge_ops.add_edge(b.id, c.id, kind="causal", root=root)
    edge_ops.add_edge(c.id, a.id, kind="causal", root=root)
    r = assess_readiness("dag", root=root)
    assert r.score == 0
    assert r.can_switch is False
    assert any(g.gap_type == "cycle_detected" for g in r.gaps)


def test_planned_type_always_zero(project):
    root, _, _, _ = project
    r = assess_readiness("influence_diagram", root=root)
    assert r.score == 0
    assert r.can_switch is False
    assert r.availability == "planned"


def test_assess_all_readiness(project):
    root, _, _, _ = project
    results = assess_all_readiness(root=root, include_planned=True)
    ids = {r.model_type_id for r in results}
    assert "cld" in ids
    assert "dag" in ids
    assert "bn" in ids


def test_assess_all_excludes_planned(project):
    root, _, _, _ = project
    results = assess_all_readiness(root=root, include_planned=False)
    ids = {r.model_type_id for r in results}
    assert "cld" in ids
    assert "dag" in ids
    assert "bn" in ids  # BN is now a stable, switchable formalism
    assert "influence_diagram" not in ids  # still-planned types remain excluded


def test_empty_graph_cld_not_ready(tmp_path: Path, git_identity, monkeypatch):
    """Empty graph with no edges has no loops, so CLD is not ready.
    A CLD without loops is incomplete by definition — the formalism's
    defining feature is feedback structure."""
    root = tmp_path / "empty"
    init_project(root, statement="Q?")
    monkeypatch.chdir(root)
    r = assess_readiness("cld", root=root)
    assert r.score == 0
    assert r.can_switch is False
    assert any(g.gap_type == "no_loops" for g in r.gaps)


# ---------------------------------------------------------------------------
# Helpers for transition readiness tests
# ---------------------------------------------------------------------------


def _make_section(section_type: str, model_type: str, generation_state: str) -> InterpretSection:
    return InterpretSection(
        id=new_id("is"),
        section_type=section_type,  # type: ignore[arg-type]
        model_type=model_type,
        generation_state=generation_state,  # type: ignore[arg-type]
    )


def _polarise_all_causal(root: Path) -> None:
    """Set polarity on every causal edge so a CLD is fully parameterised."""
    for edge in edge_ops.list_edges(root=root):
        if edge.kind == "causal":
            view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "+", root=root)


# ---------------------------------------------------------------------------
# Home → Build transition tests (transitions[0])
# ---------------------------------------------------------------------------


class TestHomeToBuild:
    def test_red_no_statement(self, tmp_path: Path, git_identity, monkeypatch):
        root = tmp_path / "proj"
        init_project(root, statement="")
        monkeypatch.chdir(root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[0]
        assert gate.from_phase == "home"
        assert gate.to_phase == "build"
        assert gate.light == "red"

    def test_green_with_statement(self, tmp_path: Path, git_identity, monkeypatch):
        """A modelling question is the only precondition — evidence is no
        longer a gate (it is an always-on resource now)."""
        root = tmp_path / "proj"
        init_project(root, statement="Does X cause Y?")
        monkeypatch.chdir(root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[0]
        assert gate.light == "green"


# ---------------------------------------------------------------------------
# Build → Formalise transition tests (transitions[1])
# ---------------------------------------------------------------------------


class TestBuildToFormalise:
    def test_red_too_few_nodes(self, tmp_path: Path, git_identity, monkeypatch):
        root = tmp_path / "proj"
        init_project(root, statement="Q?")
        monkeypatch.chdir(root)
        node_ops.add_node("A", kind="variable", root=root)
        node_ops.add_node("B", kind="variable", root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[1]
        assert gate.from_phase == "build"
        assert gate.to_phase == "formalise"
        assert gate.light == "red"
        assert any("at least 3 nodes" in d.lower() for d in gate.details)

    def test_red_no_edges(self, tmp_path: Path, git_identity, monkeypatch):
        """3 nodes but no edges → red (nothing is connected)."""
        root = tmp_path / "proj"
        init_project(root, statement="Q?")
        monkeypatch.chdir(root)
        node_ops.add_node("A", kind="variable", root=root)
        node_ops.add_node("B", kind="variable", root=root)
        node_ops.add_node("C", kind="variable", root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[1]
        assert gate.light == "red"
        assert any("edge" in d.lower() for d in gate.details)

    def test_red_orphan_node(self, tmp_path: Path, git_identity, monkeypatch):
        """3 nodes but one is disconnected → red, naming the orphan."""
        root = tmp_path / "proj"
        init_project(root, statement="Q?")
        monkeypatch.chdir(root)
        a, _ = node_ops.add_node("A", kind="variable", root=root)
        b, _ = node_ops.add_node("B", kind="variable", root=root)
        node_ops.add_node("Lonely", kind="variable", root=root)
        edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[1]
        assert gate.light == "red"
        assert any("Lonely" in d for d in gate.details)

    def test_green_unlinked_for_matrix_types(self, tmp_path: Path, git_identity, monkeypatch):
        """MCDA/ACH factors have no links: when only such types are selected, no network is required."""
        root = tmp_path / "proj"
        init_project(root, statement="Which site?")
        monkeypatch.chdir(root)
        for label in ("North", "South", "Cost"):
            node_ops.add_node(label, kind="variable", root=root)
        add_model_choice("mcda", "", root=root)
        add_model_choice("ach", "", root=root)
        add_model_choice("event_tree", "", root=root)
        gate = assess_transition_readiness(root=root).transitions[1]
        assert gate.light == "green"
        # …but a type that lives on the network brings the gate back.
        add_model_choice("cld", "", root=root)
        gate = assess_transition_readiness(root=root).transitions[1]
        assert gate.light == "red"

    def test_link_free_elements_are_not_orphans_in_a_mixed_project(self, tmp_path: Path, git_identity, monkeypatch):
        """A loop map plus MCDA: the options are unlinked by nature, so only the loop map must be connected."""
        from latris.operations import mcda

        root = tmp_path / "proj"
        init_project(root, statement="Which site?")
        monkeypatch.chdir(root)
        a, _ = node_ops.add_node("Cost", kind="variable", root=root)
        b, _ = node_ops.add_node("Demand", kind="variable", root=root)
        c, _ = node_ops.add_node("Price", kind="variable", root=root)
        edge_ops.add_edge(a.id, c.id, kind="causal", root=root)
        edge_ops.add_edge(c.id, b.id, kind="causal", root=root)
        node_ops.add_node("North site", kind="variable", root=root)
        add_model_choice("cld", "", root=root)
        add_model_choice("mcda", "", root=root)
        assert assess_transition_readiness(root=root).transitions[1].light == "red"  # North site: an orphan
        mcda.set_element("North site", "option", root=root)
        assert assess_transition_readiness(root=root).transitions[1].light == "green"

        from fastapi.testclient import TestClient

        from latris.server.app import create_app

        body = TestClient(create_app(project_root=root)).get("/api/model-types/mcda/elements").json()
        assert list(body["elements"].values()) == ["option"] and body["connected_structure"] is False

    def test_a_factor_being_formalised_is_not_an_orphan(self, sd_bathtub_root, monkeypatch):
        """A stock just added in Formalise has no links yet: SD's check reports that, not Build's gate."""
        from latris.operations import sd as sd_ops
        from latris.operations.project import add_model_choice

        root = sd_bathtub_root
        monkeypatch.chdir(root)
        add_model_choice("cld", "", root=root)
        add_model_choice("sd", "", root=root)
        node_ops.add_node("Rain", kind="variable", root=root)
        node_ops.add_node("Snow", kind="variable", root=root)
        assert assess_transition_readiness(root=root).transitions[1].light == "red"  # two unconnected factors
        sd_ops.set_role("Rain", "auxiliary", root=root)
        sd_ops.set_role("Snow", "auxiliary", root=root)
        assert assess_transition_readiness(root=root).transitions[1].light == "green"
        assert any(g.element_label == "Rain" for g in sd_ops.check(root=root))  # SD still flags it

    def test_green_connected(self, project):
        """Fixture is Price→Demand→Quantity — ≥3 nodes, single network."""
        root, _, _, _ = project
        t = assess_transition_readiness(root=root)
        gate = t.transitions[1]
        assert gate.light == "green"


# ---------------------------------------------------------------------------
# Formalise → Analyse transition tests (transitions[2])
# ---------------------------------------------------------------------------


class TestFormaliseToAnalyse:
    def test_red_no_model_types(self, project):
        root, _, _, _ = project
        t = assess_transition_readiness(root=root)
        gate = t.transitions[2]
        assert gate.from_phase == "formalise"
        assert gate.to_phase == "analyse"
        assert gate.light == "red"

    def test_red_cld_no_polarity(self, project):
        """CLD with a loop but no polarity → not fully parameterised → red."""
        root, a, b, _ = project
        edge_ops.add_edge(b.id, a.id, kind="causal", root=root)  # close the loop
        update_selected_models(["cld"], root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[2]
        assert gate.light == "red"

    def test_green_cld_fully_parameterised(self, project):
        """Loop + polarity on every causal edge → green."""
        root, a, b, _ = project
        edge_ops.add_edge(b.id, a.id, kind="causal", root=root)  # close the loop
        update_selected_models(["cld"], root=root)
        _polarise_all_causal(root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[2]
        assert gate.light == "green"

    def test_green_dag(self, project):
        """DAG has no model_attributes — an acyclic structure is enough."""
        root, _, _, _ = project
        update_selected_models(["dag"], root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[2]
        assert gate.light == "green"

    def test_yellow_mixed(self, project):
        """CLD fully parameterised + DAG made cyclic by the loop → yellow."""
        root, a, b, _ = project
        edge_ops.add_edge(b.id, a.id, kind="causal", root=root)  # loop: CLD ok, DAG cyclic
        update_selected_models(["cld", "dag"], root=root)
        _polarise_all_causal(root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[2]
        assert gate.light == "yellow"


# ---------------------------------------------------------------------------
# Analyse → Interpret transition tests (transitions[3]) — soft pass-through
# ---------------------------------------------------------------------------


class TestAnalyseToInterpret:
    def test_yellow_when_nothing_recorded(self, project):
        """Soft gate: never blocks, but nudges when no finding or analysis
        result has been recorded."""
        root, _, _, _ = project
        update_selected_models(["dag"], root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[3]
        assert gate.from_phase == "analyse"
        assert gate.to_phase == "interpret"
        assert gate.light == "yellow"
        assert any("finding add" in d for d in gate.details)
        # Yellow does not block the next gate.
        assert t.transitions[4].summary != "Blocked by an earlier phase."

    def test_green_once_a_finding_is_recorded(self, project):
        root, a, b, _ = project
        update_selected_models(["dag"], root=root)
        record_new_finding(
            "Price affects Quantity only through Demand.",
            "structure",
            "dag",
            target_ids=[a.id, b.id],
            root=root,
        )
        t = assess_transition_readiness(root=root)
        assert t.transitions[3].light == "green"


# ---------------------------------------------------------------------------
# Interpret → Communicate transition tests (transitions[4])
# ---------------------------------------------------------------------------


class TestInterpretToCommunicate:
    def _pass_earlier_gates(self, root: Path) -> None:
        """Select DAG (with a rationale) so home/build/formalise/analyse gates
        all pass on the connected acyclic fixture, and the interpret→communicate
        model-rationale nudge is satisfied."""
        add_model_choice("dag", "A DAG suits this acyclic causal question.", root=root)

    def test_red_no_sections(self, project):
        root, _, _, _ = project
        self._pass_earlier_gates(root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[4]
        assert gate.from_phase == "interpret"
        assert gate.light == "red"

    def test_yellow_structural_only(self, project):
        root, _, _, _ = project
        self._pass_earlier_gates(root)
        store = InterpretationStore(
            sections=[
                _make_section("structural_summary", "cld", "claims_only"),
            ]
        )
        save_interpretation(store, root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[4]
        assert gate.light == "yellow"

    def test_green_only_when_nothing_is_left_to_hand_over(self, project, monkeypatch):
        """Past the structural summary the light is the handover check, so the two never disagree."""
        from latris.operations import handover

        root, _, _, _ = project
        self._pass_earlier_gates(root)
        store = InterpretationStore(
            sections=[
                _make_section("structural_summary", "cld", "claims_only"),
                _make_section("answer_to_question", "cld", "generated"),
            ]
        )
        save_interpretation(store, root=root)
        left = handover.handover_check(root=root)
        gate = assess_transition_readiness(root=root).transitions[4]
        assert not left.ready and gate.light == "yellow"
        assert gate.details == [i.message for i in left.items]
        monkeypatch.setattr(handover, "handover_check", lambda **_: handover.HandoverReport("dag", True, []))
        assert assess_transition_readiness(root=root).transitions[4].light == "green"

    def test_yellow_when_model_rationale_missing(self, project):
        """A formalism selected without a recorded rationale is on the handover list, so it yellows the
        gate — the report's Modelling Approach section needs it. Never red."""
        root, _, _, _ = project
        update_selected_models(["dag"], root=root)  # selected, but no ModelChoice logged
        store = InterpretationStore(
            sections=[
                _make_section("structural_summary", "cld", "claims_only"),
                _make_section("answer_to_question", "cld", "generated"),
            ]
        )
        save_interpretation(store, root=root)
        t = assess_transition_readiness(root=root)
        gate = t.transitions[4]
        assert gate.light == "yellow"
        assert any("no reason recorded for choosing" in d for d in gate.details)


# ---------------------------------------------------------------------------
# Unified transition readiness
# ---------------------------------------------------------------------------


def test_transition_readiness_returns_five(project):
    """assess_transition_readiness returns exactly 5 TransitionStatus entries."""
    root, _, _, _ = project
    t = assess_transition_readiness(root=root)
    assert len(t.transitions) == 5
    phases = [(s.from_phase, s.to_phase) for s in t.transitions]
    assert phases == [
        ("home", "build"),
        ("build", "formalise"),
        ("formalise", "analyse"),
        ("analyse", "interpret"),
        ("interpret", "communicate"),
    ]


def test_cascade_red_propagates(tmp_path: Path, git_identity, monkeypatch):
    """If home→build is red, all subsequent transitions are forced red."""
    root = tmp_path / "proj"
    init_project(root, statement="")  # no question → home red
    monkeypatch.chdir(root)
    t = assess_transition_readiness(root=root)
    assert all(tr.light == "red" for tr in t.transitions)
    # Subsequent gates should say they're blocked by an earlier phase
    assert "earlier" in t.transitions[1].summary.lower()
