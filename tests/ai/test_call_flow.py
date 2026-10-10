"""End-to-end tests for the call orchestrator using the MockAdapter.

No network; identity via the ``git_identity`` fixture; mock responses
registered per-prompt via ``MockAdapter.shared().register_default(...)``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from latris.ai import interactions as inter_ops
from latris.ai import proposals as proposal_module
from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.cli.app import app
from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo import git


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    yield
    MockAdapter.reset_shared()


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
    attr_ops.set_attribute(a.id, "description", "Posted retail price.", root=root)
    monkeypatch.chdir(root)
    return root, a, b, edge


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


# ---------- ExplainThisElement ----------


def test_explain_logs_but_does_not_mutate(project) -> None:
    root, a, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.ExplanationResult,
        result=ChatResult(
            parsed=proposal_module.ExplanationResult(
                explanation="Price is a driver node in the causal framing.",
                referenced_ids=[a.id],
            ),
            raw="Price is a driver node in the causal framing.",
            model_id="claude-opus-4-6",
            token_usage={"input_tokens": 50, "output_tokens": 12},
            cost_usd=0.0012,
        ),
    )
    before = _commit_count(root)
    result = CliRunner().invoke(app, ["ai", "call", "explain", a.id, "--yes"])
    assert result.exit_code == 0, result.output
    # One commit: the interaction + approval.  (interaction record + approval → 2 commits)
    after = _commit_count(root)
    assert after - before in (1, 2)  # record_interaction commits; set_approval commits

    # The output mentions approved and no applied IDs
    assert "approved" in result.output.lower()

    # Log picked it up
    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    assert records[0].prompt_name == "ExplainThisElement"
    assert records[0].adoption == "approved"
    assert records[0].response_full and "driver node" in records[0].response_full
    assert records[0].token_usage.get("input_tokens") == 50
    assert records[0].cost_usd == pytest.approx(0.0012)


# ---------- ChallengeThisConnection ----------


def test_challenge_approved_opens_challenge(project) -> None:
    root, _, _, edge = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.ChallengeProposal,
        result=ChatResult(
            parsed=proposal_module.ChallengeProposal(
                target_id=edge.id,
                target_attribute="polarity",
                argument="Reverse causality may run from demand to price.",
                opening_turn="Consider the simultaneity bias in retail data.",
                recommended_state="retained-with-caveat",
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
            token_usage={"input_tokens": 100, "output_tokens": 40},
            cost_usd=0.002,
        ),
    )
    before = _commit_count(root)
    result = CliRunner().invoke(app, ["ai", "call", "challenge", edge.id, "-a", "polarity", "--yes"])
    assert result.exit_code == 0, result.output
    after = _commit_count(root)
    # Commits: open_challenge + add_turn + record_interaction + set_approval
    assert after > before + 1

    # A Challenge was opened
    from latris.operations import challenges as ch_ops

    challenges = ch_ops.list_challenges(root=root)
    assert len(challenges) == 1
    assert challenges[0].argument.startswith("Reverse")
    assert len(challenges[0].conversation) == 1

    records = inter_ops.list_interactions(root=root)
    assert records[0].adoption == "approved"
    assert records[0].proposal_ids  # has the created challenge id


def test_challenge_rejected_skips_mutation(project) -> None:
    root, _, _, edge = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.ChallengeProposal,
        result=ChatResult(
            parsed=proposal_module.ChallengeProposal(
                target_id=edge.id,
                target_attribute="polarity",
                argument="Weak argument.",
                opening_turn=None,
                recommended_state=None,
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    # Don't pass --yes; feed `n` on stdin.
    result = CliRunner().invoke(
        app,
        ["ai", "call", "challenge", edge.id, "-a", "polarity"],
        input="n\n",
    )
    assert result.exit_code == 0, result.output

    from latris.operations import challenges as ch_ops

    assert ch_ops.list_challenges(root=root) == []  # no challenge opened

    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    assert records[0].adoption == "rejected"


# ---------- SuggestCitations ----------


def test_suggest_citations_approved_adds_refs_and_evidence(project) -> None:
    root, a, _, _ = project
    ref_ops.add_reference("existing2024", title="An existing ref", root=root)

    MockAdapter.shared().register_default(
        response_cls=proposal_module.CitationsProposal,
        result=ChatResult(
            parsed=proposal_module.CitationsProposal(
                new_references=[
                    proposal_module.CitationSuggestion(
                        bibkey="smith2023",
                        title="Pricing studies",
                        authors=["Smith, J."],
                        year=2023,
                        doi="10.1000/x",
                    ),
                ],
                evidence_links=[
                    proposal_module.EvidenceAttachment(
                        target_id=a.id,
                        attribute="description",
                        bibkey="smith2023",
                        rationale="Defines retail pricing concept.",
                    ),
                    proposal_module.EvidenceAttachment(
                        target_id=a.id,
                        attribute="description",
                        bibkey="existing2024",
                        rationale="Contains related framing.",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(
        app,
        ["ai", "call", "suggest-citations", a.id, "description", "--yes"],
    )
    assert result.exit_code == 0, result.output

    # New ref added; evidence links attached
    refs = {r.bibkey for r in ref_ops.list_references(root=root)}
    assert "smith2023" in refs
    assert "existing2024" in refs

    # Approved state
    records = inter_ops.list_interactions(root=root)
    assert records[0].adoption == "approved"
    assert records[0].proposal_ids  # applied ids populated


def test_suggest_citations_refuses_fabricated_bibkey(project) -> None:
    """Safety rail: an evidence_link whose bibkey is neither in the library
    nor in new_references must be refused by the apply layer."""
    root, a, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.CitationsProposal,
        result=ChatResult(
            parsed=proposal_module.CitationsProposal(
                new_references=[],  # no new refs declared
                evidence_links=[
                    proposal_module.EvidenceAttachment(
                        target_id=a.id,
                        attribute="description",
                        bibkey="fabricated2999",  # DOES NOT EXIST anywhere
                        rationale="AI invented this.",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(
        app,
        ["ai", "call", "suggest-citations", a.id, "description", "--yes"],
    )
    # The apply raises ValueError — our CLI error handler surfaces exit 2.
    assert result.exit_code != 0

    # No new reference; no evidence attached
    assert ref_ops.list_references(root=root) == []
    # But the rejection WAS logged for memory
    records = inter_ops.list_interactions(root=root)
    assert len(records) == 1
    assert records[0].adoption == "rejected"
    assert "safety rail" in records[0].response_summary.lower()


# ---------- DraftConceptualModel ----------


def test_draft_approved_creates_nodes_and_edges(project) -> None:
    root, a, b, edge = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.DraftModelProposal,
        result=ChatResult(
            parsed=proposal_module.DraftModelProposal(
                framings=[
                    proposal_module.DraftFraming(
                        name="Supply-side",
                        entities=[
                            proposal_module.DraftEntity(label="Supply", kind="variable"),
                        ],
                        edges=[
                            proposal_module.DraftEdge(from_label="Supply", to_label="Demand", kind="causal"),
                        ],
                        rationale="Add supply dimension.",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    # --yes auto-selects index 0
    result = CliRunner().invoke(
        app,
        ["ai", "call", "draft", "pricing model", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()

    nodes = node_ops.list_nodes(root)
    labels = {n.label for n in nodes}
    assert "Supply" in labels


# ---------- AttackThisModel ----------


def test_attack_hybrid_prose_and_mutation(project) -> None:
    """AttackThisModel is now hybrid: prose critique AND a bounded mutation
    that records the named weakest assumption + an optional follow-up
    question."""
    root, a, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.AttackResult,
        result=ChatResult(
            parsed=proposal_module.AttackResult(
                weakest_assumption="Market is liquid",
                argument="Evidence from 2008 suggests otherwise.",
                affected_node_ids=[a.id],
                recommended_action="Add liquidity constraint node.",
                follow_up_question="Does liquidity hold under stress conditions?",
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(app, ["ai", "call", "attack", "--yes"])
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()
    assert "Market is liquid" in result.output  # prose still rendered
    # Mutation: the weakest assumption is recorded as an Assumption
    # and the follow-up is logged as an OpenQuestion.
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema import AssumptionLog, QuestionLog

    paths = ProjectPaths(root)
    a_log = load_model(AssumptionLog, paths.assumptions_yaml) if paths.assumptions_yaml.exists() else AssumptionLog()
    q_log = load_model(QuestionLog, paths.questions_yaml) if paths.questions_yaml.exists() else QuestionLog()
    assert any("Market is liquid" in a.statement for a in a_log.entries)
    assert any("liquidity hold" in q.question for q in q_log.entries)


# ---------- ScopeCheck ----------


def test_scope_check_hybrid_prose_and_mutation(project) -> None:
    root, _, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.ScopeCheckResult,
        result=ChatResult(
            parsed=proposal_module.ScopeCheckResult(
                verdict="well-matched",
                suggestions=[],
                reasoning="The model adequately covers the foundation question.",
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(app, ["ai", "call", "scope-check", "--yes"])
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()
    assert "well-matched" in result.output


# ---------- FindNewConnections ----------


def test_find_connections_approved(project) -> None:
    root, a, b, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.NewConnectionsProposal,
        result=ChatResult(
            parsed=proposal_module.NewConnectionsProposal(
                proposals=[
                    proposal_module.EdgeProposal(
                        from_id=b.id,
                        to_id=a.id,
                        kind="causal",
                        rationale="Demand feeds back to price.",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    # --yes auto-approves all
    result = CliRunner().invoke(
        app,
        ["ai", "call", "find-connections", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()

    edges = edge_ops.list_edges(root)
    # Original edge + new edge
    assert len(edges) == 2


# ---------- SyntheticPeerReview ----------


def test_peer_review_read_only(project) -> None:
    root, _, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.PeerReviewResult,
        result=ChatResult(
            parsed=proposal_module.PeerReviewResult(
                reviewer_role="domain expert",
                scope_assessment="Scope is adequate for the research question.",
                rigor_assessment="Causal claims are plausible but lack mediation detail.",
                evidence_assessment="Evidence is thin — only one reference.",
                major_risks=["Single-source dependency"],
                proposed_questions=["What confounders have you considered?"],
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(app, ["ai", "call", "peer-review", "--yes"])
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()
    assert "Scope is adequate" in result.output

    records = inter_ops.list_interactions(root=root)
    assert records[0].prompt_name == "SyntheticPeerReview"
    assert records[0].adoption == "approved"


# ---------- IdentifyResearchGaps ----------


def test_research_gaps_hybrid_prose_and_mutation(project) -> None:
    root, a, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.ResearchGapsResult,
        result=ChatResult(
            parsed=proposal_module.ResearchGapsResult(
                gaps=[
                    proposal_module.ResearchGap(
                        description="No evidence for the Price→Demand mechanism.",
                        priority="high",
                        affected_node_ids=[a.id],
                        suggested_action="Add empirical reference for price elasticity.",
                    ),
                ],
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(app, ["ai", "call", "research-gaps", "--yes"])
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()
    assert "No evidence for the Price" in result.output

    records = inter_ops.list_interactions(root=root)
    assert records[0].prompt_name == "IdentifyResearchGaps"


# ---------- SteelmanOpposingView ----------


def test_steelman_approved_adds_contested_view(project) -> None:
    root, a, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.SteelmanProposal,
        result=ChatResult(
            parsed=proposal_module.SteelmanProposal(
                target_id=a.id,
                opposing_view="Price is endogenous; it is a consequence, not a cause.",
                rationale="Equilibrium pricing theory suggests price is determined by supply-demand.",
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    before = _commit_count(root)
    result = CliRunner().invoke(app, ["ai", "call", "steelman", a.id, "--yes"])
    assert result.exit_code == 0, result.output
    after = _commit_count(root)
    assert after > before

    # Verify contested view was added to the description attribute
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema import DescriptionSet

    paths = ProjectPaths(root)
    desc_set = load_model(DescriptionSet, paths.descriptions_yaml)
    entry = next(e for e in desc_set.entries if e.target_id == a.id)
    assert entry.contested is True
    assert len(entry.contested_views) == 1
    assert "endogenous" in entry.contested_views[0]

    records = inter_ops.list_interactions(root=root)
    assert records[0].adoption == "approved"


def test_steelman_rejected_skips_mutation(project) -> None:
    root, a, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.SteelmanProposal,
        result=ChatResult(
            parsed=proposal_module.SteelmanProposal(
                target_id=a.id,
                opposing_view="Weak view.",
                rationale="",
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(
        app,
        ["ai", "call", "steelman", a.id],
        input="n\n",
    )
    assert result.exit_code == 0, result.output

    # No contested view added
    from latris.repo.layout import ProjectPaths
    from latris.repo.yaml_io import load_model
    from latris.schema import DescriptionSet

    paths = ProjectPaths(root)
    desc_set = load_model(DescriptionSet, paths.descriptions_yaml)
    entry = next(e for e in desc_set.entries if e.target_id == a.id)
    assert entry.contested is False
    assert entry.contested_views == []

    records = inter_ops.list_interactions(root=root)
    assert records[0].adoption == "rejected"


# ---------- ProjectToFormalView ----------


def test_project_view_read_only(project) -> None:
    root, _, _, _ = project
    MockAdapter.shared().register_default(
        response_cls=proposal_module.FormalViewProjectionResult,
        result=ChatResult(
            parsed=proposal_module.FormalViewProjectionResult(
                target_view="cld",
                recommended_mappings=[{"entity": "Price", "include": "yes"}],
                conflicts=["Edge Price→Demand missing polarity for CLD."],
                rationale="CLD requires polarity on all edges.",
            ),
            raw="(raw)",
            model_id="claude-opus-4-6",
        ),
    )
    result = CliRunner().invoke(app, ["ai", "call", "project-view", "cld", "--yes"])
    assert result.exit_code == 0, result.output
    assert "approved" in result.output.lower()
    assert "cld" in result.output.lower()

    records = inter_ops.list_interactions(root=root)
    assert records[0].prompt_name == "ProjectToFormalView"


# ---------- dry-run ----------


def test_dry_run_does_not_call_adapter_or_mutate(project) -> None:
    root, a, _, _ = project
    # No mock registered — would raise on a real call, proving no call happens.
    result = CliRunner().invoke(
        app,
        ["ai", "call", "explain", a.id, "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output.lower()
    # No interaction logged
    assert inter_ops.list_interactions(root=root) == []
