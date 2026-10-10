"""Tests for AI proposal apply() dispatchers (ai/proposals.py).

Every AI mutation flows through ``proposal.apply(paths)``. These tests
verify each proposal type creates the correct operations-layer mutations,
and — critically — that the citation fabrication safety rail works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai.proposals import (
    AssumptionsProposal,
    ChallengeProposal,
    CitationsProposal,
    CitationSuggestion,
    DecisionEntry,
    DecisionsProposal,
    DraftAssumption,
    DraftEdge,
    DraftEntity,
    DraftFraming,
    DraftModelProposal,
    EdgeProposal,
    ExclusionEntry,
    ExclusionsProposal,
    ExpandBibliographyProposal,
    ExtractedClaim,
    NewConnectionsProposal,
    ProvenanceBundle,
    QuestionEntry,
    QuestionsProposal,
    SteelmanProposal,
    SuggestedConnection,
)
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.operations.references import add_reference, list_references
from latris.repo.layout import ProjectPaths


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Test?")
    return root


@pytest.fixture
def paths(project: Path) -> ProjectPaths:
    return ProjectPaths(project)


# ── ChallengeProposal ──────────────────────────────────────────────


class TestChallengeProposal:
    def test_creates_challenge(self, project: Path, paths: ProjectPaths) -> None:
        node, _ = node_ops.add_node("Price", root=project)
        proposal = ChallengeProposal(
            target_id=node.id,
            argument="Price may not be the real driver.",
        )
        ids = proposal.apply(paths)
        assert len(ids) >= 1
        assert ids[0].startswith("challenge_")

    def test_with_opening_turn(self, project: Path, paths: ProjectPaths) -> None:
        node, _ = node_ops.add_node("X", root=project)
        proposal = ChallengeProposal(
            target_id=node.id,
            argument="Questionable.",
            opening_turn="Let me elaborate on why.",
        )
        ids = proposal.apply(paths)
        assert len(ids) >= 1

    def test_with_provenance_bundle(self, project: Path, paths: ProjectPaths) -> None:
        node, _ = node_ops.add_node("Y", root=project)
        proposal = ChallengeProposal(
            target_id=node.id,
            argument="Weak link.",
            provenance=ProvenanceBundle(
                assumptions=[DraftAssumption(statement="Assumed linear")],
                questions=[QuestionEntry(question="What about nonlinear?")],
            ),
        )
        ids = proposal.apply(paths)
        # challenge + 1 assumption + 1 question
        assert len(ids) == 3


# ── CitationsProposal ──────────────────────────────────────────────


class TestCitationsProposal:
    def test_adds_new_references_and_evidence(self, project: Path, paths: ProjectPaths) -> None:
        node, _ = node_ops.add_node("Demand", root=project)
        proposal = CitationsProposal(
            new_references=[
                CitationSuggestion(bibkey="smith2020", title="Smith on Demand"),
            ],
            evidence_links=[
                # Use the mock evidence attachment
                _evidence("Demand", "description", "smith2020"),
            ],
        )
        # resolve by label won't work here — evidence needs the actual ID
        proposal.evidence_links[0].target_id = node.id
        ids = proposal.apply(paths)
        assert "smith2020" in ids

    def test_fabrication_guard_rejects_unknown_bibkey(self, project: Path, paths: ProjectPaths) -> None:
        node, _ = node_ops.add_node("X", root=project)
        proposal = CitationsProposal(
            new_references=[],  # no new refs
            evidence_links=[
                _evidence(node.id, "description", "fabricated2099"),
            ],
        )
        with pytest.raises(ValueError, match="refusing to apply.*fabricated2099"):
            proposal.apply(paths)

    def test_ai_proposed_evidence_has_conservative_audit_axes(
        self, project: Path, paths: ProjectPaths
    ) -> None:
        """AI-proposed evidence links must default to verified_by=ai,
        source_access=title_only, support_verdict=unverified — the
        AI never read the source at proposal time. The capability run
        labelled AI-proposed links 'ai-verified' which conflated
        proposer with claim-level verification; Phase 1 keeps these
        axes orthogonal."""
        from latris.repo.yaml_io import load_model
        from latris.schema import EvidenceLinkSet

        node, _ = node_ops.add_node("Demand", root=project)
        proposal = CitationsProposal(
            new_references=[CitationSuggestion(bibkey="ai2024", title="AI Demand")],
            evidence_links=[_evidence("Demand", "description", "ai2024")],
        )
        proposal.evidence_links[0].target_id = node.id
        proposal.apply(paths)

        store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        link = next(e for e in store.entries if e.bibkey == "ai2024")
        assert link.verified_by == "ai"
        assert link.source_access == "title_only"
        assert link.support_verdict == "unverified"
        assert link.quote is None

    def test_skips_refs_already_in_library(self, project: Path, paths: ProjectPaths) -> None:
        add_reference("existing2020", "Existing Paper", root=project)
        proposal = CitationsProposal(
            new_references=[
                CitationSuggestion(bibkey="existing2020", title="Dup", already_in_library=False),
                CitationSuggestion(bibkey="new2021", title="New Paper"),
            ],
            evidence_links=[],
        )
        ids = proposal.apply(paths)
        # Only the new one should be added
        assert "new2021" in ids
        assert "existing2020" not in ids
        # Library should have both
        refs = list_references(project)
        bibkeys = {r.bibkey for r in refs}
        assert "existing2020" in bibkeys
        assert "new2021" in bibkeys


# ── DraftModelProposal ─────────────────────────────────────────────


class TestDraftModelProposal:
    def test_creates_nodes_and_edges(self, project: Path, paths: ProjectPaths) -> None:
        proposal = DraftModelProposal(
            framings=[
                DraftFraming(
                    name="Simple",
                    entities=[
                        DraftEntity(label="Rain", kind="concept"),
                        DraftEntity(label="Flood", kind="concept"),
                    ],
                    edges=[
                        DraftEdge(from_label="Rain", to_label="Flood", kind="causal"),
                    ],
                ),
            ],
            selected_index=0,
        )
        ids = proposal.apply(paths)
        assert len(ids) == 3  # 2 nodes + 1 edge
        labels = [n.label for n in node_ops.list_nodes(project)]
        assert "Rain" in labels
        assert "Flood" in labels

    def test_no_selection_raises(self, paths: ProjectPaths) -> None:
        proposal = DraftModelProposal(framings=[DraftFraming(name="X")])
        with pytest.raises(ValueError, match="No framing selected"):
            proposal.apply(paths)

    def test_out_of_range_index_raises(self, paths: ProjectPaths) -> None:
        proposal = DraftModelProposal(
            framings=[DraftFraming(name="Only")],
            selected_index=5,
        )
        with pytest.raises(ValueError, match="out of range"):
            proposal.apply(paths)

    def test_skips_duplicate_labels(self, project: Path, paths: ProjectPaths) -> None:
        node_ops.add_node("Existing", root=project)
        proposal = DraftModelProposal(
            framings=[
                DraftFraming(
                    name="Overlap",
                    entities=[DraftEntity(label="Existing"), DraftEntity(label="New")],
                    edges=[],
                ),
            ],
            selected_index=0,
        )
        ids = proposal.apply(paths)
        # Only "New" should be created
        assert len(ids) == 1

    def test_skips_edges_with_unresolvable_labels(self, project: Path, paths: ProjectPaths) -> None:
        proposal = DraftModelProposal(
            framings=[
                DraftFraming(
                    name="Broken",
                    entities=[DraftEntity(label="A")],
                    edges=[DraftEdge(from_label="A", to_label="Missing")],
                ),
            ],
            selected_index=0,
        )
        ids = proposal.apply(paths)
        # Node A created, but edge silently skipped
        assert len(ids) == 1

    def test_invalid_node_kind_rejected_by_schema(self) -> None:
        # DraftEntity.kind is now typed EntityKind, so an invalid kind is
        # rejected at parse time (the structured-output layer forces the model
        # to retry) rather than being silently coerced at apply. This is the
        # stronger guarantee introduced in the prompt rework.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DraftEntity(label="X", kind="nonsense_kind")

    def test_invalid_edge_kind_falls_back(self, project: Path, paths: ProjectPaths) -> None:
        # Edge kind is still a free string coerced at apply, so a bogus edge
        # kind falls back to a valid default rather than dropping the edge.
        proposal = DraftModelProposal(
            framings=[
                DraftFraming(
                    name="BadEdgeKind",
                    entities=[
                        DraftEntity(label="X"),
                        DraftEntity(label="Y"),
                    ],
                    edges=[
                        DraftEdge(from_label="X", to_label="Y", kind="fake_edge"),
                    ],
                ),
            ],
            selected_index=0,
        )
        ids = proposal.apply(paths)
        assert len(ids) == 3  # X, Y, and the edge (kind coerced)

    def test_creates_assumptions(self, project: Path, paths: ProjectPaths) -> None:
        proposal = DraftModelProposal(
            framings=[
                DraftFraming(
                    name="WithAssumptions",
                    entities=[DraftEntity(label="Z")],
                    edges=[],
                    assumptions=[DraftAssumption(statement="Assumed linear")],
                ),
            ],
            selected_index=0,
        )
        ids = proposal.apply(paths)
        # 1 node + 1 assumption
        assert len(ids) == 2


# ── NewConnectionsProposal ─────────────────────────────────────────


class TestNewConnectionsProposal:
    def test_applies_approved_indices(self, project: Path, paths: ProjectPaths) -> None:
        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        c, _ = node_ops.add_node("C", root=project)
        proposal = NewConnectionsProposal(
            proposals=[
                EdgeProposal(from_id=a.id, to_id=b.id, rationale="A→B"),
                EdgeProposal(from_id=b.id, to_id=c.id, rationale="B→C"),
                EdgeProposal(from_id=a.id, to_id=c.id, rationale="A→C"),
            ],
            approved_indices=[0, 2],  # skip index 1
        )
        proposal.apply(paths)
        edges = edge_ops.list_edges(project)
        assert len(edges) == 2

    def test_no_approval_raises(self, paths: ProjectPaths) -> None:
        proposal = NewConnectionsProposal(
            proposals=[EdgeProposal(from_id="x", to_id="y")],
        )
        with pytest.raises(ValueError, match="No proposals approved"):
            proposal.apply(paths)

    def test_out_of_range_indices_skipped(self, project: Path, paths: ProjectPaths) -> None:
        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        proposal = NewConnectionsProposal(
            proposals=[EdgeProposal(from_id=a.id, to_id=b.id)],
            approved_indices=[0, 99],  # 99 is out of range
        )
        proposal.apply(paths)
        assert len(edge_ops.list_edges(project)) == 1


# ── SteelmanProposal ───────────────────────────────────────────────


def test_steelman_adds_contested_view(project: Path, paths: ProjectPaths) -> None:
    node, _ = node_ops.add_node("Traffic", root=project)
    # Need a description for the contested view to attach to
    from latris.operations.attributes import set_attribute

    set_attribute(node.id, "description", "Vehicular traffic", root=project)

    proposal = SteelmanProposal(
        target_id=node.id,
        opposing_view="Could also represent data traffic.",
    )
    ids = proposal.apply(paths)
    assert node.id in ids


# ── Provenance proposals ───────────────────────────────────────────


def test_assumptions_proposal(project: Path, paths: ProjectPaths) -> None:
    node, _ = node_ops.add_node("X", root=project)
    proposal = AssumptionsProposal(
        target_id=node.id,
        assumptions=[
            DraftAssumption(statement="Linear relationship"),
            DraftAssumption(statement="No feedback loops"),
        ],
    )
    ids = proposal.apply(paths)
    assert len(ids) == 2


def test_decisions_proposal(project: Path, paths: ProjectPaths) -> None:
    node, _ = node_ops.add_node("X", root=project)
    proposal = DecisionsProposal(
        target_id=node.id,
        decisions=[DecisionEntry(statement="Include X", rationale="Scoping decision")],
    )
    ids = proposal.apply(paths)
    assert len(ids) == 1


def test_exclusions_proposal(project: Path, paths: ProjectPaths) -> None:
    proposal = ExclusionsProposal(
        exclusions=[ExclusionEntry(statement="Ignore Y", rationale="Out of scope")],
    )
    ids = proposal.apply(paths)
    assert len(ids) == 1


def test_questions_proposal(project: Path, paths: ProjectPaths) -> None:
    node, _ = node_ops.add_node("X", root=project)
    proposal = QuestionsProposal(
        target_id=node.id,
        questions=[QuestionEntry(question="Is X measurable?")],
    )
    ids = proposal.apply(paths)
    assert len(ids) == 1


# ── ExpandBibliographyProposal ─────────────────────────────────────


def test_expand_bibliography_adds_new_skips_existing(project: Path, paths: ProjectPaths) -> None:
    add_reference("old2020", "Old Paper", root=project)
    proposal = ExpandBibliographyProposal(
        new_references=[
            CitationSuggestion(bibkey="old2020", title="Old Paper"),
            CitationSuggestion(bibkey="new2021", title="New Paper"),
        ],
    )
    created = proposal.apply(paths)
    assert "new2021" in created
    assert "old2020" not in created


# ── Compose extraction kind validation ──────────────────────────────


def test_extracted_variable_rejects_unknown_kind() -> None:
    """Compose AI must emit one of the 7 substrate EntityKinds, not CLD roles."""
    from pydantic import ValidationError

    from latris.ai.proposals import ExtractedVariable

    with pytest.raises(ValidationError):
        ExtractedVariable(label="Nitrogen Inputs", kind="driver")


def test_suggested_variable_rejects_unknown_kind() -> None:
    from pydantic import ValidationError

    from latris.ai.proposals import SuggestedVariable

    with pytest.raises(ValidationError):
        SuggestedVariable(label="Lever X", kind="lever")


def test_extracted_variable_accepts_substrate_kinds() -> None:
    from latris.ai.proposals import ExtractedVariable

    for kind in ("concept", "variable", "event", "actor", "state", "decision", "hazard"):
        ExtractedVariable(label="t", kind=kind)


# ── Per-entity provenance capture (assumptions / source_bibkeys / polarity) ──


class TestEntityProvenanceCapture:
    """The structural proposals capture provenance in the same act as the edit:
    assumptions bind to the created node/edge, source_bibkeys become evidence
    links (fabricated bibkeys skipped), and CLD polarity + rationale co-author."""

    def _cld_project(self, tmp_path: Path, git_identity) -> ProjectPaths:
        root = tmp_path / "proj"
        init_project(root, statement="Q?")
        from latris.operations.project import update_selected_models

        update_selected_models(["cld"], root=root)
        add_reference("smith2020", "Smith", root=root)
        return ProjectPaths(root)

    def test_draft_binds_assumptions_evidence_and_polarity(self, tmp_path: Path, git_identity) -> None:
        from latris.repo.yaml_io import load_model
        from latris.schema import AssumptionLog, EvidenceLinkSet, PolaritySet

        paths = self._cld_project(tmp_path, git_identity)
        proposal = DraftModelProposal(
            selected_index=0,
            framings=[
                DraftFraming(
                    name="F",
                    entities=[
                        DraftEntity(
                            label="Fertiliser use",
                            kind="variable",
                            source_bibkeys=["smith2020", "ghost2099"],  # 2nd is fabricated
                            confidence="high",
                            assumptions=[DraftAssumption(statement="linear response")],
                        ),
                        DraftEntity(label="Algal blooms", kind="variable"),
                    ],
                    edges=[
                        DraftEdge(
                            from_label="Fertiliser use",
                            to_label="Algal blooms",
                            description="more nutrients increase blooms",
                            polarity="+",
                            polarity_rationale="nutrient loading drives algal growth",
                            source_bibkeys=["smith2020"],
                            assumptions=[DraftAssumption(statement="no P limitation")],
                        )
                    ],
                )
            ],
        )
        proposal.apply(paths)

        nodes = {n.label: n.id for n in node_ops.list_nodes(paths.root)}
        edges = edge_ops.list_edges(paths.root)
        assert len(edges) == 1
        edge_id = edges[0].id

        # Assumptions bind to their specific element — including the EDGE, which
        # was impossible before (framing assumptions only ever resolved to nodes).
        assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
        by_target = {a.target_id: a.statement for a in assumptions}
        assert by_target.get(nodes["Fertiliser use"]) == "linear response"
        assert by_target.get(edge_id) == "no P limitation"

        # source_bibkeys → evidence links; the fabricated bibkey is skipped.
        ev = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries
        linked = {(e.target_id, e.bibkey) for e in ev}
        assert (nodes["Fertiliser use"], "smith2020") in linked
        assert (edge_id, "smith2020") in linked
        assert not any(bib == "ghost2099" for _, bib in linked)
        assert all(e.verified_by == "ai" for e in ev)

        # Polarity + rationale co-authored into the CLD store.
        pol = {p.target_id: p for p in load_model(PolaritySet, paths.view_attribute_path("cld", "polarity")).entries}
        assert pol[edge_id].value == "+"
        assert pol[edge_id].rationale == "nutrient loading drives algal growth"

    def test_draft_apply_is_a_single_commit(self, tmp_path: Path, git_identity) -> None:
        from latris.repo import git

        paths = self._cld_project(tmp_path, git_identity)
        before = len(git.run_git(["log", "--oneline"], cwd=paths.root).stdout.splitlines())
        proposal = DraftModelProposal(
            selected_index=0,
            framings=[
                DraftFraming(
                    name="F",
                    entities=[DraftEntity(label="A", kind="variable"), DraftEntity(label="B", kind="variable")],
                    edges=[DraftEdge(from_label="A", to_label="B", description="a drives b", polarity="+")],
                )
            ],
        )
        proposal.apply(paths)
        after = len(git.run_git(["log", "--oneline"], cwd=paths.root).stdout.splitlines())
        assert after - before == 1  # one batch commit, not one per write

    def test_new_connections_binds_assumptions_to_the_edge(self, tmp_path: Path, git_identity) -> None:
        from latris.repo.yaml_io import load_model
        from latris.schema import AssumptionLog, EvidenceLinkSet

        paths = self._cld_project(tmp_path, git_identity)
        a, _ = node_ops.add_node("A", root=paths.root)
        b, _ = node_ops.add_node("B", root=paths.root)
        proposal = NewConnectionsProposal(
            proposals=[
                EdgeProposal(
                    from_id=a.id,
                    to_id=b.id,
                    description="a increases b",
                    polarity="+",
                    polarity_rationale="a directly raises b",
                    source_bibkeys=["smith2020"],
                    assumptions=[DraftAssumption(statement="ceteris paribus")],
                )
            ],
            approved_indices=[0],
        )
        proposal.apply(paths)
        edges = edge_ops.list_edges(paths.root)
        assert len(edges) == 1
        edge_id = edges[0].id
        assumptions = load_model(AssumptionLog, paths.assumptions_yaml).entries
        # The old code dumped this with target_id=None; it must now bind to the edge.
        assert any(x.target_id == edge_id and x.statement == "ceteris paribus" for x in assumptions)
        ev = load_model(EvidenceLinkSet, paths.evidence_links_yaml).entries
        assert any(e.target_id == edge_id and e.bibkey == "smith2020" for e in ev)


# ── Non-destructive value-set + free collections ────────────────────


class TestNonDestructiveValueSet:
    """AI value-set calls (unique attributes) never clobber an existing value:
    they fill gaps, and on disagreement record a question rather than overwrite.
    Collection provenance stays free to accumulate."""

    def _cld_edge(self, tmp_path: Path, git_identity):
        root = tmp_path / "proj"
        init_project(root, statement="Q?")
        from latris.operations.project import update_selected_models

        update_selected_models(["cld"], root=root)
        a, _ = node_ops.add_node("A", kind="variable", root=root)
        b, _ = node_ops.add_node("B", kind="variable", root=root)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=root)
        return ProjectPaths(root), edge.id

    def _suggest(self, edge_id: str, value: str):
        from latris.ai.proposals import AttributeSuggestion, AttributeSuggestionsResult

        return AttributeSuggestionsResult(
            suggestions=[
                AttributeSuggestion(edge_id=edge_id, attribute="polarity", value=value, rationale="A drives B")
            ]
        )

    def _polarity(self, paths: ProjectPaths, edge_id: str):
        from latris.operations.view_attributes import get_view_attributes

        return {e.target_id: e.value for e in get_view_attributes("cld", "polarity", root=paths.root).entries}.get(
            edge_id
        )

    def _questions_on(self, paths: ProjectPaths, edge_id: str):
        from latris.repo.yaml_io import load_model
        from latris.schema import QuestionLog

        return [q for q in load_model(QuestionLog, paths.questions_yaml).entries if q.target_id == edge_id]

    def test_fills_gap_when_no_existing_polarity(self, tmp_path: Path, git_identity) -> None:
        paths, edge_id = self._cld_edge(tmp_path, git_identity)
        self._suggest(edge_id, "+").apply(paths)
        assert self._polarity(paths, edge_id) == "+"
        assert not self._questions_on(paths, edge_id)

    def test_preserves_existing_and_records_conflict(self, tmp_path: Path, git_identity) -> None:
        from latris.operations.view_attributes import set_view_attribute

        paths, edge_id = self._cld_edge(tmp_path, git_identity)
        set_view_attribute(edge_id, "cld", "polarity", "+", root=paths.root)  # existing value
        self._suggest(edge_id, "-").apply(paths)  # AI disagrees
        assert self._polarity(paths, edge_id) == "+"  # NOT clobbered
        qs = self._questions_on(paths, edge_id)
        assert len(qs) == 1 and "polarity" in qs[0].question  # disagreement recorded

    def test_same_value_is_noop(self, tmp_path: Path, git_identity) -> None:
        from latris.operations.view_attributes import set_view_attribute

        paths, edge_id = self._cld_edge(tmp_path, git_identity)
        set_view_attribute(edge_id, "cld", "polarity", "+", root=paths.root)
        self._suggest(edge_id, "+").apply(paths)  # agrees
        assert self._polarity(paths, edge_id) == "+"
        assert not self._questions_on(paths, edge_id)  # no noise

    def test_collections_are_not_deduped(self, tmp_path: Path, git_identity) -> None:
        """Provenance collections stay free — the AI may keep adding; we did NOT
        add a dedup barrier for assumptions/questions/etc."""
        from latris.operations.provenance import add_assumption
        from latris.repo.yaml_io import load_model
        from latris.schema import AssumptionLog

        root = tmp_path / "proj"
        init_project(root, statement="Q?")
        n, _ = node_ops.add_node("A", kind="variable", root=root)
        add_assumption("first assumption", target_id=n.id, root=root)
        add_assumption("second assumption", target_id=n.id, root=root)
        entries = load_model(AssumptionLog, ProjectPaths(root).assumptions_yaml).entries
        assert sum(1 for a in entries if a.target_id == n.id) == 2


# ── Helpers ─────────────────────────────────────────────────────────


def _evidence(target_id: str, attribute: str, bibkey: str):
    from latris.ai.proposals import EvidenceAttachment

    return EvidenceAttachment(
        target_id=target_id,
        attribute=attribute,
        bibkey=bibkey,
        rationale="Test rationale",
    )


# ── EdgeReclassifyProposal (Phase 3a) ──────────────────────────────────


class TestEdgeReclassifyProposal:
    def test_retag_changes_edge_kind(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import (
            EdgeReclassifyAction,
            EdgeReclassifyProposal,
        )

        a, _ = node_ops.add_node("Firm Revenue", root=project)
        b, _ = node_ops.add_node("4DWW", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        # The 4DWW capability run misclassified this exact pattern as
        # causal — the prompt's job is to retag it.
        proposal = EdgeReclassifyProposal(
            actions=[
                EdgeReclassifyAction(
                    target_id=edge.id,
                    action="retag",
                    new_kind="decision_rule",
                    rationale="budget allocation rule, not causal mechanism",
                    confidence="high",
                )
            ],
        )
        affected = proposal.apply(paths)
        assert affected == [edge.id]
        retyped = next(e for e in edge_ops.list_edges(project) if e.id == edge.id)
        assert retyped.kind == "decision_rule"

    def test_remove_records_rationale_in_commit(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import (
            EdgeReclassifyAction,
            EdgeReclassifyProposal,
        )
        from latris.repo import git

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        proposal = EdgeReclassifyProposal(
            actions=[
                EdgeReclassifyAction(
                    target_id=edge.id,
                    action="remove",
                    rationale="this is not a real relation, just narrative noise",
                    confidence="medium",
                )
            ],
        )
        proposal.apply(paths)
        assert edge_ops.list_edges(project) == []
        body = git.run_git(["log", "-1", "--format=%B"], cwd=project).stdout
        assert "rationale: this is not a real relation" in body

    def test_keep_action_is_a_noop(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import (
            EdgeReclassifyAction,
            EdgeReclassifyProposal,
        )

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        proposal = EdgeReclassifyProposal(
            actions=[
                EdgeReclassifyAction(
                    target_id=edge.id,
                    action="keep",
                    rationale="correctly causal",
                    confidence="high",
                )
            ],
        )
        affected = proposal.apply(paths)
        assert affected == []
        # Edge unchanged.
        assert next(e for e in edge_ops.list_edges(project) if e.id == edge.id).kind == "causal"

    def test_approved_indices_filters_subset(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import (
            EdgeReclassifyAction,
            EdgeReclassifyProposal,
        )

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        c, _ = node_ops.add_node("C", root=project)
        e_ab, _ = edge_ops.add_edge(a.id, b.id, root=project)
        e_bc, _ = edge_ops.add_edge(b.id, c.id, root=project)
        proposal = EdgeReclassifyProposal(
            actions=[
                EdgeReclassifyAction(target_id=e_ab.id, action="retag", new_kind="governance", rationale="r1"),
                EdgeReclassifyAction(target_id=e_bc.id, action="retag", new_kind="definitional", rationale="r2"),
            ],
            approved_indices=[1],
        )
        proposal.apply(paths)
        edges = {e.id: e.kind for e in edge_ops.list_edges(project)}
        assert edges[e_ab.id] == "causal"
        assert edges[e_bc.id] == "definitional"

    def test_invalid_action_raises(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import (
            EdgeReclassifyAction,
            EdgeReclassifyProposal,
        )

        proposal = EdgeReclassifyProposal(
            actions=[
                EdgeReclassifyAction(target_id="edge_x", action="banana", rationale="r")
            ],
        )
        with pytest.raises(ValueError, match="invalid action"):
            proposal.apply(paths)

    def test_invalid_retag_kind_raises(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import (
            EdgeReclassifyAction,
            EdgeReclassifyProposal,
        )

        # Retag to a v2+ kind (flow) — outside the constrained target set.
        proposal = EdgeReclassifyProposal(
            actions=[
                EdgeReclassifyAction(
                    target_id="edge_x",
                    action="retag",
                    new_kind="flow",
                    rationale="r",
                )
            ],
        )
        with pytest.raises(ValueError, match="invalid new_kind"):
            proposal.apply(paths)


# ── ChallengeEdgeProposal (Phase 3b) ───────────────────────────────────


class TestChallengeEdgeProposal:
    def test_evidence_search_records_question(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import ChallengeEdgeProposal
        from latris.repo.yaml_io import load_model
        from latris.schema import QuestionLog

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        proposal = ChallengeEdgeProposal(
            target_id=edge.id,
            action="evidence_search",
            summary="Counter-mechanism: confounder X",
            search_query="four-day work week productivity meta-analysis",
            rationale="need a meta-analysis to settle the sign",
            confidence="high",
        )
        affected = proposal.apply(paths)
        assert len(affected) == 1
        questions = load_model(QuestionLog, paths.questions_yaml).entries
        assert any("four-day work week productivity meta-analysis" in q.question for q in questions)

    def test_polarity_flip_sets_view_attribute(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import ChallengeEdgeProposal
        from latris.operations.view_attributes import get_view_attributes

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        proposal = ChallengeEdgeProposal(
            target_id=edge.id,
            action="polarity_flip",
            new_polarity="-",
            rationale="counter-mechanism implies negative sign",
            confidence="medium",
            model_type="cld",
        )
        proposal.apply(paths)
        polarities = get_view_attributes("cld", "polarity", root=project)
        assert any(p.target_id == edge.id and p.value == "-" for p in polarities.entries)

    def test_remove_action_removes_edge_with_rationale(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import ChallengeEdgeProposal
        from latris.repo import git

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        proposal = ChallengeEdgeProposal(
            target_id=edge.id,
            action="remove",
            rationale="counter-mechanism makes the edge irrelevant",
            confidence="medium",
        )
        proposal.apply(paths)
        assert edge_ops.list_edges(project) == []
        body = git.run_git(["log", "-1", "--format=%B"], cwd=project).stdout
        assert "rationale: counter-mechanism makes the edge irrelevant" in body

    def test_polarity_flip_rejects_invalid_polarity(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import ChallengeEdgeProposal

        proposal = ChallengeEdgeProposal(
            target_id="edge_x",
            action="polarity_flip",
            new_polarity="??",
            rationale="r",
        )
        with pytest.raises(ValueError, match="polarity_flip requires new_polarity"):
            proposal.apply(paths)

    def test_evidence_search_requires_query(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import ChallengeEdgeProposal

        proposal = ChallengeEdgeProposal(
            target_id="edge_x",
            action="evidence_search",
            search_query=None,
            rationale="r",
        )
        with pytest.raises(ValueError, match="evidence_search requires search_query"):
            proposal.apply(paths)

    def test_invalid_action_raises(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import ChallengeEdgeProposal

        proposal = ChallengeEdgeProposal(
            target_id="edge_x",
            action="banana",
        )
        with pytest.raises(ValueError, match="invalid action"):
            proposal.apply(paths)


# ── EvidenceDemoteProposal (Phase 3b) ──────────────────────────────────


class TestEvidenceDemoteProposal:
    def test_change_verdict_via_proposal(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import EvidenceDemoteProposal
        from latris.operations import evidence as evidence_ops
        from latris.operations import references as ref_ops
        from latris.repo.yaml_io import load_model
        from latris.schema import EvidenceLinkSet

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        ref_ops.add_reference("smith2023", title="X", root=project)
        evidence_ops.add_evidence(edge.id, "polarity", "smith2023", root=project)

        proposal = EvidenceDemoteProposal(
            target_id=edge.id,
            attribute="polarity",
            bibkey="smith2023",
            action="change_verdict",
            new_verdict="orthogonal",
            rationale="paper discusses elasticity, not the polarity claim",
            confidence="high",
        )
        proposal.apply(paths)
        store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        link = next(e for e in store.entries if e.bibkey == "smith2023")
        assert link.support_verdict == "orthogonal"

    def test_remove_via_proposal_records_rationale(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import EvidenceDemoteProposal
        from latris.operations import evidence as evidence_ops
        from latris.operations import references as ref_ops
        from latris.repo import git

        a, _ = node_ops.add_node("A", root=project)
        b, _ = node_ops.add_node("B", root=project)
        edge, _ = edge_ops.add_edge(a.id, b.id, root=project)
        ref_ops.add_reference("doe2024", title="Y", root=project)
        evidence_ops.add_evidence(edge.id, "polarity", "doe2024", root=project)

        proposal = EvidenceDemoteProposal(
            target_id=edge.id,
            attribute="polarity",
            bibkey="doe2024",
            action="remove",
            rationale="misleading citation; source has nothing to do with the claim",
            confidence="high",
        )
        proposal.apply(paths)
        body = git.run_git(["log", "-1", "--format=%B"], cwd=project).stdout
        assert "rationale: misleading citation" in body

    def test_change_verdict_rejects_invalid_verdict(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import EvidenceDemoteProposal

        proposal = EvidenceDemoteProposal(
            target_id="x",
            attribute="polarity",
            bibkey="b",
            action="change_verdict",
            new_verdict="banana",
            rationale="r",
        )
        with pytest.raises(ValueError, match="change_verdict requires new_verdict"):
            proposal.apply(paths)

    def test_invalid_action_raises(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import EvidenceDemoteProposal

        proposal = EvidenceDemoteProposal(
            target_id="x",
            attribute="polarity",
            bibkey="b",
            action="banana",
        )
        with pytest.raises(ValueError, match="invalid action"):
            proposal.apply(paths)


# ── VerifyClaimAgainstSourceProposal (Phase 4a) ────────────────────────


class TestVerifyClaimAgainstSourceProposal:
    """The audit invariant: the apply()-time verbatim check is the
    source of truth on whether a source supports a claim. The model
    cannot self-attest — its quote is rejected if not present in the
    stored extract."""

    @staticmethod
    def _setup_link_with_snapshot(project: Path, extract: str):
        """Helper: create a node + reference + evidence link with a
        populated source_snapshot extract."""
        from latris.operations import evidence as evidence_ops
        from latris.operations import references as ref_ops

        a, _ = node_ops.add_node("Air Quality", root=project)
        ref_ops.add_reference("smith2023", title="Air quality study", root=project)
        ref_ops.set_source_snapshot(
            "smith2023",
            extract=extract,
            retrieval_url="https://example.org/snap",
            kind="abstract",
            root=project,
        )
        evidence_ops.add_evidence(a.id, "description", "smith2023", root=project)
        return a

    def test_supports_with_verbatim_quote_promotes_link(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal
        from latris.repo.yaml_io import load_model
        from latris.schema import EvidenceLinkSet

        extract = (
            "Vehicle emissions are a primary driver of urban air quality "
            "decline. Studies show NO2 levels rise during rush hour."
        )
        a = self._setup_link_with_snapshot(project, extract)

        proposal = VerifyClaimAgainstSourceProposal(
            target_id=a.id,
            attribute="description",
            bibkey="smith2023",
            claim="Vehicle emissions affect air quality",
            verdict="supports",
            quote="Vehicle emissions are a primary driver of urban air quality decline.",
            rationale="exact match",
            confidence="high",
        )
        affected = proposal.apply(paths)
        assert len(affected) == 1

        store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        link = next(e for e in store.entries if e.bibkey == "smith2023")
        assert link.support_verdict == "supports"
        assert link.quote is not None
        assert link.quote.startswith("Vehicle emissions are a primary driver")
        assert link.quote_location is not None
        assert link.quote_location.offset == 0
        assert link.quote_location.chunk_hash.startswith("sha256:")
        # source_access bumps from abstract → full_text_chunk
        assert link.source_access == "full_text_chunk"

    def test_verbatim_mismatch_rejects_proposal(self, project: Path, paths: ProjectPaths) -> None:
        """Audit invariant: paraphrased quote must be rejected. Link
        state must remain unchanged so substrate stays trustworthy."""
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal
        from latris.repo.yaml_io import load_model
        from latris.schema import EvidenceLinkSet

        extract = "Vehicle emissions decline air quality."
        a = self._setup_link_with_snapshot(project, extract)

        proposal = VerifyClaimAgainstSourceProposal(
            target_id=a.id,
            attribute="description",
            bibkey="smith2023",
            claim="Cars cause smog",
            verdict="supports",
            quote="Cars cause smog",  # NOT in extract — paraphrase
            rationale="paraphrased the source",
            confidence="high",
        )
        with pytest.raises(ValueError, match="verbatim mismatch"):
            proposal.apply(paths)

        # Link is unchanged.
        store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        link = next(e for e in store.entries if e.bibkey == "smith2023")
        assert link.support_verdict == "unverified"
        assert link.quote is None
        assert link.quote_location is None

    def test_supports_without_quote_raises(self, project: Path, paths: ProjectPaths) -> None:
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal

        self._setup_link_with_snapshot(project, "some text")
        a = node_ops.list_nodes(project)[0]
        proposal = VerifyClaimAgainstSourceProposal(
            target_id=a.id,
            attribute="description",
            bibkey="smith2023",
            claim="X",
            verdict="supports",
            quote=None,  # missing
            rationale="r",
        )
        with pytest.raises(ValueError, match="requires a verbatim quote"):
            proposal.apply(paths)

    def test_missing_snapshot_raises_at_apply(self, project: Path, paths: ProjectPaths) -> None:
        """When the Reference has no source_snapshot.extract, the
        apply()-time validator can't compare anything — must reject."""
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal
        from latris.operations import evidence as evidence_ops
        from latris.operations import references as ref_ops

        a, _ = node_ops.add_node("Air Quality", root=project)
        ref_ops.add_reference("smith2023", title="X", root=project)
        # No set_source_snapshot — extract is None.
        evidence_ops.add_evidence(a.id, "description", "smith2023", root=project)

        proposal = VerifyClaimAgainstSourceProposal(
            target_id=a.id,
            attribute="description",
            bibkey="smith2023",
            claim="X",
            verdict="supports",
            quote="anything",
            rationale="r",
        )
        with pytest.raises(ValueError, match="no source_snapshot.extract"):
            proposal.apply(paths)

    def test_orthogonal_verdict_skips_verbatim_check(self, project: Path, paths: ProjectPaths) -> None:
        """Non-supports verdicts don't need a quote. They just flip the
        verdict via set_evidence_support_verdict."""
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal
        from latris.repo.yaml_io import load_model
        from latris.schema import EvidenceLinkSet

        a = self._setup_link_with_snapshot(project, "Vehicle emissions affect air quality.")
        proposal = VerifyClaimAgainstSourceProposal(
            target_id=a.id,
            attribute="description",
            bibkey="smith2023",
            claim="X",
            verdict="orthogonal",
            quote=None,
            rationale="source is on-topic but does not address this claim",
            confidence="high",
        )
        proposal.apply(paths)
        store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        link = next(e for e in store.entries if e.bibkey == "smith2023")
        assert link.support_verdict == "orthogonal"
        assert link.quote is None  # no quote on non-supports

    def test_invalid_verdict_raises(self, paths: ProjectPaths) -> None:
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal

        proposal = VerifyClaimAgainstSourceProposal(
            target_id=None,
            attribute="x",
            bibkey="b",
            claim="X",
            verdict="banana",
            rationale="r",
        )
        with pytest.raises(ValueError, match="invalid verdict"):
            proposal.apply(paths)

    def test_supports_validates_against_chunk_when_artefact_exists(
        self, project: Path, paths: ProjectPaths
    ) -> None:
        """Phase 4b: when the per-bibkey extract artefact exists, the
        validator looks up the matching chunk and records the chunk's
        content_hash + global offset on the link's QuoteLocation."""
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal
        from latris.operations import evidence as evidence_ops
        from latris.operations import references as ref_ops
        from latris.repo.yaml_io import load_model
        from latris.schema import EvidenceLinkSet

        a, _ = node_ops.add_node("Air Quality", root=project)
        ref_ops.add_reference("smith2023", title="X", url="https://e/x", root=project)
        # Build a long body so chunking actually splits it.
        body = (
            "Filler content. " * 80
            + "Vehicle emissions are a primary driver of urban air quality decline. "
            + "More filler. " * 80
        )

        class _Resp:
            def __init__(self, text):
                self.text = text
                self.content = text.encode("utf-8")
                self.headers = {"content-type": "text/plain"}
                self.url = "https://e/x"

            def raise_for_status(self):
                return None

        ref_ops.fetch_reference_source(
            "smith2023",
            http_get=lambda *_a, **_k: _Resp(body),
            root=project,
        )
        evidence_ops.add_evidence(a.id, "description", "smith2023", root=project)

        proposal = VerifyClaimAgainstSourceProposal(
            target_id=a.id,
            attribute="description",
            bibkey="smith2023",
            claim="Vehicle emissions affect air quality",
            verdict="supports",
            quote="Vehicle emissions are a primary driver of urban air quality decline.",
            rationale="exact match in the fetched full text",
            confidence="high",
        )
        proposal.apply(paths)

        store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        link = next(e for e in store.entries if e.bibkey == "smith2023")
        assert link.support_verdict == "supports"
        assert link.quote_location is not None
        # When chunked, chunk_hash points at a chunk, not the snapshot's hash.
        assert link.quote_location.chunk_hash != link.quote_location.chunk_hash[:0]
        # Offset is global (chunk.offset + position-in-chunk), not just
        # within-chunk.
        assert link.quote_location.offset > 0

    def test_chunked_verbatim_mismatch_rejects(
        self, project: Path, paths: ProjectPaths
    ) -> None:
        from latris.ai.proposals import VerifyClaimAgainstSourceProposal
        from latris.operations import evidence as evidence_ops
        from latris.operations import references as ref_ops
        from latris.repo.yaml_io import load_model
        from latris.schema import EvidenceLinkSet

        a, _ = node_ops.add_node("Air Quality", root=project)
        ref_ops.add_reference("s", title="X", url="https://e/x", root=project)

        class _Resp:
            text = "Vehicle emissions affect air quality. Studies confirm."
            content = text.encode("utf-8")
            headers = {"content-type": "text/plain"}
            url = "https://e/x"

            def raise_for_status(self):
                return None

        ref_ops.fetch_reference_source(
            "s", http_get=lambda *_a, **_k: _Resp(), root=project,
        )
        evidence_ops.add_evidence(a.id, "description", "s", root=project)

        proposal = VerifyClaimAgainstSourceProposal(
            target_id=a.id,
            attribute="description",
            bibkey="s",
            claim="X",
            verdict="supports",
            quote="Cars cause global warming",  # NOT in the fetched text
            rationale="hallucination",
            confidence="high",
        )
        with pytest.raises(ValueError, match="any chunk of the fetched source"):
            proposal.apply(paths)
        store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        link = next(e for e in store.entries if e.bibkey == "s")
        assert link.support_verdict == "unverified"


# ── Edge proposal description fields ───────────────────────────────


class TestEdgeProposalDescriptions:
    """ExtractedClaim and SuggestedConnection must carry an explicit
    `description` field (the mechanism), distinct from `rationale`
    (the extraction/suggestion reason). Compose relies on this."""

    def test_extracted_claim_description_round_trip(self) -> None:
        claim = ExtractedClaim(
            from_label="Rainfall",
            to_label="Runoff",
            kind="causal",
            description="Higher rainfall increases surface runoff volume.",
            rationale="Smith 2024 explicitly states this mechanism.",
            source_bibkeys=["smith2024"],
            claim_text="Rainfall is the primary driver of runoff.",
        )
        dumped = claim.model_dump()
        assert dumped["description"] == "Higher rainfall increases surface runoff volume."
        loaded = ExtractedClaim.model_validate(dumped)
        assert loaded.description == claim.description
        assert loaded.rationale == claim.rationale

    def test_extracted_claim_description_defaults_to_empty(self) -> None:
        claim = ExtractedClaim(from_label="A", to_label="B")
        assert claim.description == ""

    def test_suggested_connection_description_round_trip(self) -> None:
        conn = SuggestedConnection(
            from_label="A",
            to_label="B",
            kind="causal",
            description="A drives B via mechanism X.",
            rationale="Closes the missing balancing loop.",
            confidence="high",
        )
        dumped = conn.model_dump()
        assert dumped["description"] == "A drives B via mechanism X."
        loaded = SuggestedConnection.model_validate(dumped)
        assert loaded.description == conn.description
        assert loaded.rationale == conn.rationale

    def test_suggested_connection_description_defaults_to_empty(self) -> None:
        conn = SuggestedConnection(from_label="A", to_label="B")
        assert conn.description == ""
