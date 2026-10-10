"""Byte-identical round-trip for every schema model.

Contract: for any valid instance ``m`` of a schema model,
``dump(m) == dump(load(dump(m)))`` at the byte level. This guarantees clean
git diffs for human-edited YAML files — saving a file you just loaded never
changes its bytes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    AIInteraction,
    AnalysisRun,
    Assumption,
    AssumptionLog,
    Challenge,
    ChallengeLog,
    ColumnSpec,
    ConfidenceEntry,
    ConfidenceSet,
    ConversationTurn,
    CPTEntry,
    CPTRow,
    CPTSet,
    DataAction,
    DataActionLog,
    Dataset,
    DatasetLibrary,
    DatasetVersion,
    DatasetVersionLibrary,
    Decision,
    DecisionLog,
    DescriptionEntry,
    DescriptionSet,
    Edge,
    ElicitationIndexEntry,
    ElicitationLog,
    ElicitationSession,
    Entity,
    EvidenceLink,
    EvidenceLinkSet,
    Exclusion,
    ExclusionLog,
    ExpertActor,
    FloatEntry,
    FloatSet,
    HumanActor,
    Informants,
    LineageNode,
    Mapping,
    MappingRegistry,
    Milestone,
    MilestoneLog,
    ParameterUncertainty,
    ParameterUncertaintySet,
    PolarityEntry,
    PolaritySet,
    Prediction,
    PredictionLog,
    ProjectFoundation,
    Question,
    QuestionLog,
    QuoteLocation,
    Reference,
    ReferenceLibrary,
    RoleEntry,
    RoleSet,
    Session,
    SessionLog,
    Signoff,
    SignoffLog,
    SourceSnapshot,
    StateSpaceEntry,
    StateSpaceSet,
    Substrate,
    View,
    new_id,
)
from latris.schema.elicitation import (
    ElicitationProtocol,
    ExpertResponse,
    TargetAttribute,
)
from latris.schema.review import (
    ReviewerInfo,
    ReviewFeedbackItem,
    ReviewManifest,
    ReviewSession,
    ReviewSessionLog,
)
from latris.schema.settings import BNSettings, FCMSettings, MarkovSettings, SDSettings

FIXED_DT = datetime(2026, 4, 15, 12, 30, 45, tzinfo=UTC)
FIXED_DATE = date(2026, 4, 15)
ALICE = HumanActor(name="Alice Example", email="alice@example.com")
BOB = HumanActor(name="Bob Example")
EXPERT_DR_SMITH = ExpertActor(
    name="Dr. Smith",
    email="smith@university.edu",
    credentials="PhD epidemiology, 15y NHS",
    affiliation="University of Oxford",
    calibration_score=0.85,
)


def _fixtures() -> dict[str, BaseModel]:
    """Return one populated instance per model we expect to round-trip."""
    node_a = Entity(id=new_id("node"), kind="variable", label="Price")
    node_b = Entity(id=new_id("node"), kind="variable", label="Demand")
    edge = Edge(id=new_id("edge"), from_id=node_a.id, to_id=node_b.id, kind="causal")

    return {
        "project": ProjectFoundation(
            statement="Does price reliably influence demand in context Z?",
        ),
        "references_empty": ReferenceLibrary(),
        "references_populated": ReferenceLibrary(
            entries=[
                Reference(
                    bibkey="smith2023",
                    title="A study — on em-dashes",
                    authors=["Smith, J."],
                    year=2023,
                    doi="10.1000/x",
                ),
                Reference(
                    bibkey="doe2024",
                    title="Another",
                    authors=["Doe, J.", "Roe, R."],
                    year=2024,
                    url="https://example.org/doe",
                ),
            ]
        ),
        "references_with_snapshot": ReferenceLibrary(
            entries=[
                Reference(
                    bibkey="abstract2025",
                    title="Paper with abstract snapshot",
                    abstract="Existing abstract field.",
                    source_snapshot=SourceSnapshot(
                        retrieval_url="https://example.org/abstract2025",
                        fetched_at=FIXED_DT,
                        content_hash="sha256:beefcafe",
                        extract="Captured first paragraph of the abstract page…",
                        kind="abstract",
                    ),
                ),
                Reference(
                    bibkey="landing2025",
                    title="Paper with landing-page snapshot",
                    source_snapshot=SourceSnapshot(
                        retrieval_url="https://example.org/landing2025",
                        fetched_at=FIXED_DT,
                        content_hash="sha256:deadbeef",
                        extract="Generic publisher landing page text.",
                        kind="landing_page_text",
                    ),
                ),
            ]
        ),
        "substrate_empty": Substrate(),
        "substrate_populated": Substrate(entities=[node_a, node_b], edges=[edge]),
        "mappings": MappingRegistry(
            entries=[
                Mapping(l2_id=node_a.id, l3_view="cld", l3_id=node_a.id, origin="ai-proposed", maturity="approved"),
            ]
        ),
        "descriptions": DescriptionSet(
            entries=[
                DescriptionEntry(
                    target_id=node_a.id,
                    value="The posted retail price.",
                    informants=Informants(proposed_by=[ALICE]),
                ),
            ]
        ),
        "confidence": ConfidenceSet(
            entries=[
                ConfidenceEntry(target_id=edge.id, value="medium"),
            ]
        ),
        "polarity": PolaritySet(
            entries=[
                PolarityEntry(target_id=edge.id, value="-"),
            ]
        ),
        "roles_empty": RoleSet(),
        "float_empty": FloatSet(),
        "float_populated": FloatSet(
            entries=[
                FloatEntry(target_id=edge.id, attribute="weight", value=0.7),
                FloatEntry(target_id=node_a.id, attribute="weight", value=-0.3),
            ]
        ),
        "roles_populated": RoleSet(
            entries=[
                RoleEntry(target_id=node_a.id, value="stock"),
                RoleEntry(target_id=node_b.id, value="auxiliary"),
            ]
        ),
        "uncertainty_empty": ParameterUncertaintySet(),
        "uncertainty_populated": ParameterUncertaintySet(
            entries=[
                ParameterUncertainty(
                    target_id=edge.id,
                    distribution="beta",
                    params={"alpha": 2.0, "beta": 5.0},
                    parameter_cell_id="cell_01EXAMPLE",
                ),
            ]
        ),
        "settings_sd": SDSettings(dt=0.5, final_time=50.0),
        "settings_fcm": FCMSettings(lambda_steepness=2.0, max_iterations=200),
        "settings_markov": MarkovSettings(num_cycles=40, discount_rate=0.03),
        "settings_bn": BNSettings(),
        "bn_state_spaces": StateSpaceSet(
            entries=[
                StateSpaceEntry(target_id=node_a.id, states=["low", "high"]),
                StateSpaceEntry(
                    target_id=node_b.id,
                    states=["low", "med", "high"],
                    ordered=True,
                    origin="human-elicited",
                ),
            ]
        ),
        "bn_cpts": CPTSet(
            entries=[
                CPTEntry(
                    target_id=node_a.id,
                    parents=[],
                    states=["low", "high"],
                    rows=[CPTRow(parent_states={}, p=[0.3, 0.7])],
                ),
                CPTEntry(
                    target_id=node_b.id,
                    parents=[node_a.id],
                    states=["low", "med", "high"],
                    rows=[
                        CPTRow(
                            parent_states={node_a.id: "low"},
                            p=[0.6, 0.3, 0.1],
                            origin="human-elicited",
                            source_id="src_smith2021",
                        ),
                        CPTRow(
                            parent_states={node_a.id: "high"},
                            p=[0.1, 0.3, 0.6],
                            origin="ai-proposed",
                            contested=True,
                        ),
                    ],
                ),
            ]
        ),
        "evidence": EvidenceLinkSet(
            entries=[
                EvidenceLink(
                    target_id=edge.id,
                    attribute="polarity",
                    bibkey="smith2023",
                    verified_by="human",
                    source_access="full_text",
                    support_verdict="supports",
                    quote="Lower prices increase demand in liquid markets.",
                    quote_location=QuoteLocation(
                        chunk_hash="sha256:abc123",
                        page=12,
                        offset=440,
                    ),
                    informants=Informants(approved_by=[ALICE]),
                ),
            ]
        ),
        "view_cld": View(kind="cld", entity_ids=[node_a.id, node_b.id], edge_ids=[edge.id], notes="Base CLD."),
        "view_dag": View(kind="dag", entity_ids=[node_a.id, node_b.id], edge_ids=[edge.id]),
        "assumptions": AssumptionLog(
            entries=[
                Assumption(
                    id=new_id("assumption"),
                    statement="Market is liquid.",
                    rationale="Per industry norm.",
                    authored_by=ALICE,
                ),
            ]
        ),
        "decisions": DecisionLog(
            entries=[
                Decision(
                    id=new_id("decision"),
                    statement="Excluded macroeconomic shocks.",
                    rationale="Out of scope for Q1 window.",
                    authored_by=ALICE,
                ),
            ]
        ),
        "signoffs": SignoffLog(
            entries=[
                Signoff(
                    id=new_id("signoff"),
                    reviewer=BOB,
                    role="Senior reviewer",
                    scope="Substrate v0.1",
                    signed_at=FIXED_DT,
                ),
            ]
        ),
        "sessions": SessionLog(
            entries=[
                Session(id=new_id("session"), held_at=date(2026, 4, 10), attendees=[ALICE, BOB], notes="Kickoff."),
            ]
        ),
        "questions": QuestionLog(
            entries=[
                Question(
                    id=new_id("question"), question="Does seasonality apply?", raised_by=ALICE
                ),
            ]
        ),
        "exclusions": ExclusionLog(
            entries=[
                Exclusion(
                    id=new_id("exclusion"),
                    statement="No cross-border effects.",
                    rationale="Scope of study.",
                    authored_by=ALICE,
                ),
            ]
        ),
        "predictions": PredictionLog(
            entries=[
                Prediction(
                    id=new_id("prediction"),
                    statement="Demand drops 8% within 6 months.",
                    horizon="6 months",
                    authored_by=ALICE,
                ),
            ]
        ),
        "challenges": ChallengeLog(
            entries=[
                Challenge(
                    id=new_id("challenge"),
                    target_id=edge.id,
                    argument="Price is co-determined with demand — the edge direction is arguable.",
                    conversation=[
                        ConversationTurn(speaker=ALICE, message="Consider the simultaneity bias.", at=FIXED_DT),
                    ],
                    state="open",
                    opened_by=ALICE,
                ),
            ]
        ),
        "ai_interaction": AIInteraction(
            id=new_id("interaction"),
            prompt_name="DraftConceptualModel",
            prompt_inputs={"seed": "pricing-demand", "count": 3},
            model_id="claude-opus-4-6",
            response_summary="Generated 3 candidate framings.",
            proposal_ids=[],
            adoption="pending",
        ),
        # -- M11: provenance axes on existing models --
        "entity_with_provenance": Substrate(
            entities=[
                Entity(
                    id=new_id("node"),
                    kind="variable",
                    label="Emissions",
                    origin="data-derived",
                    verification="human-verified",
                    source_id="analysis-run_01EXAMPLE",
                ),
            ]
        ),
        "edge_with_provenance": Substrate(
            edges=[
                Edge(
                    id=new_id("edge"),
                    from_id="node_A",
                    to_id="node_B",
                    kind="causal",
                    origin="ai-proposed",
                    verification="unverified",
                    source_id="interaction_01EXAMPLE",
                ),
            ]
        ),
        "description_with_provenance": DescriptionSet(
            entries=[
                DescriptionEntry(
                    target_id="node_X",
                    value="Sourced from expert elicitation.",
                    origin="human-elicited",
                    verification="human-verified",
                    source_id="elicitation_01EXAMPLE",
                    informants=Informants(proposed_by=[EXPERT_DR_SMITH]),
                ),
            ]
        ),
        "evidence_with_provenance": EvidenceLinkSet(
            entries=[
                EvidenceLink(
                    target_id="edge_Y",
                    attribute="polarity",
                    bibkey="jones2024",
                    origin="ai-proposed",
                    verified_by="ai",
                    source_access="abstract",
                    support_verdict="orthogonal",
                    source_id="interaction_01EXAMPLE",
                ),
            ]
        ),
        # -- M11: new schema stubs --
        "expert_actor_in_informants": DescriptionSet(
            entries=[
                DescriptionEntry(
                    target_id="node_Z",
                    value="Expert-contributed.",
                    informants=Informants(
                        proposed_by=[EXPERT_DR_SMITH],
                        approved_by=[ALICE],
                    ),
                ),
            ]
        ),
        "elicitation_log_empty": ElicitationLog(),
        "elicitation_log_populated": ElicitationLog(
            entries=[
                ElicitationIndexEntry(
                    id="elicitation_01EXAMPLE",
                    file_path="provenance/elicitations/2026-04-15-delphi-pricing.yaml",
                ),
            ]
        ),
        "elicitation_session": ElicitationSession(
            id=new_id("elicitation"),
            held_at=FIXED_DATE,
            facilitator=ALICE,
            experts=[EXPERT_DR_SMITH],
            protocol=ElicitationProtocol(
                name="delphi",
                rounds_planned=3,
                anonymous=True,
                aggregation_method="median",
            ),
            target_attributes=[TargetAttribute(target_id="node_X", attribute="confidence")],
            raw_responses=[
                ExpertResponse(
                    expert=EXPERT_DR_SMITH,
                    round=1,
                    raw_input="high confidence based on 10 years of field data",
                    rationale="Direct observation in 3 sites",
                    submitted_at=FIXED_DT,
                ),
            ],
            aggregated_result={"confidence": "high"},
            confidence_summary="High agreement among 1 expert.",
            phase="active",
        ),
        "dataset_library_empty": DatasetLibrary(),
        "dataset_library_populated": DatasetLibrary(
            entries=[
                Dataset(
                    id=new_id("dataset"),
                    name="pricing-data",
                    description="Monthly pricing data 2020-2025",
                    source_type="file",
                    location="data/files/pricing-data.csv",
                    schema_info={"columns": ["date", "price", "volume"]},
                    rows=1200,
                    license="CC-BY-4.0",
                    storage_policy="committed",
                    registered_by=ALICE,
                ),
            ]
        ),
        "lineage_node": LineageNode(
            id=new_id("version"),
            name="CLD after workshop",
            maturity="proposed",
            relationship="original",
            created_by=ALICE,
            notes="Initial version.",
        ),
        "lineage_node_alternative": LineageNode(
            id=new_id("version"),
            name="What-if: remove feedback loop",
            relationship="alternative",
            created_by=BOB,
        ),
        "lineage_node_archived": LineageNode(
            id=new_id("version"),
            name="Superseded line",
            relationship="alternative",
            created_by=BOB,
            archived=True,
            superseded_by=new_id("version"),
        ),
        "milestone": Milestone(
            id=new_id("milestone"),
            name="Pre-workshop baseline",
            commit_sha="a" * 40,
            maturity="proposed",
            created_by=ALICE,
            notes="Stable state before Tuesday's session.",
        ),
        "milestone_log_empty": MilestoneLog(),
        "milestone_log_populated": MilestoneLog(
            entries=[
                Milestone(
                    id=new_id("milestone"),
                    name="Draft 1",
                    commit_sha="b" * 40,
                    created_by=ALICE,
                ),
            ]
        ),
        "analysis_run": AnalysisRun(
            id=new_id("analysis-run"),
            run_by=ALICE,
            purpose="structure-learning",
            algorithm="pgmpy.HillClimbSearch",
            library_version="pgmpy==0.1.25",
            hyperparameters={"scoring_method": "BIC", "max_indegree": 3},
            seed=42,
            input_dataset_ids=["dataset_01EXAMPLE"],
            input_model_commit="abc123def",
            target_view="dag",
            output_summary="Learned 5 edges from 1200 rows.",
            output_artifacts=["analysis/outputs/run_01/learned-structure.yaml"],
            metrics={"bic": -1234.5, "edges_added": 5},
            affected_target_ids=["edge_01", "edge_02"],
            duration_seconds=12.5,
        ),
        # -- Data wrangling: columns, actions, versions --
        "dataset_with_columns": DatasetLibrary(
            entries=[
                Dataset(
                    id=new_id("dataset"),
                    name="survey-results",
                    description="Customer satisfaction survey Q1 2026",
                    source_type="file",
                    location="data/files/survey-results.csv",
                    rows=500,
                    columns=[
                        ColumnSpec(name="respondent_id", dtype="int64", role="id"),
                        ColumnSpec(name="satisfaction", dtype="float64", role="target", description="1-5 Likert scale"),
                        ColumnSpec(name="region", dtype="string", role="feature"),
                    ],
                    storage_policy="committed",
                    registered_by=ALICE,
                ),
            ]
        ),
        "data_action_log_empty": DataActionLog(dataset_id="dataset_01EXAMPLE"),
        "data_action_log_populated": DataActionLog(
            dataset_id="dataset_01EXAMPLE",
            entries=[
                DataAction(
                    id=new_id("data-action"),
                    dataset_id="dataset_01EXAMPLE",
                    kind="rename_column",
                    params={"column": "col_0", "new_name": "price"},
                    summary='Renamed column "col_0" to "price"',
                    rows_before=1200,
                    rows_after=1200,
                    columns_affected=["col_0", "price"],
                    performed_by=ALICE,
                    commit_sha="a" * 40,
                ),
                DataAction(
                    id=new_id("data-action"),
                    dataset_id="dataset_01EXAMPLE",
                    kind="drop_nan_rows",
                    params={"columns": ["price"], "how": "any"},
                    summary='Dropped 47 NaN rows from column "price"',
                    rows_before=1200,
                    rows_after=1153,
                    columns_affected=["price"],
                    performed_by=ALICE,
                    commit_sha="b" * 40,
                ),
            ],
        ),
        # -- Review pack --
        "review_session_log_empty": ReviewSessionLog(),
        "review_session_log_populated": ReviewSessionLog(
            entries=[
                ReviewSession(
                    id=new_id("review-session"),
                    export_commit_sha="abc123def",
                    exported_at=FIXED_DT,
                    exported_by=ALICE,
                    pack="review",
                    sections=["foundation", "nodes", "edges"],
                    item_count=3,
                ),
            ]
        ),
        "review_session_imported": ReviewSessionLog(
            entries=[
                ReviewSession(
                    id=new_id("review-session"),
                    export_commit_sha="abc123def",
                    import_commit_sha="def456abc",
                    exported_at=FIXED_DT,
                    imported_at=FIXED_DT,
                    exported_by=ALICE,
                    reviewer=ReviewerInfo(name="Dr. Smith", email="smith@uni.edu", role="Domain Expert"),
                    pack="audit",
                    sections=["foundation", "nodes", "edges", "evidence", "challenges"],
                    item_count=5,
                    phase="imported",
                ),
            ]
        ),
        "review_manifest": ReviewManifest(
            review_session_id=new_id("review-session"),
            project_name="demo-project",
            export_commit_sha="abc123def",
            exported_at=FIXED_DT,
            exported_by=ALICE,
            pack="review",
            sections=["foundation", "nodes", "edges"],
            element_ids={"node_01": "Price", "node_02": "Demand"},
            reviewer=ReviewerInfo(name="Bob"),
            items=[
                ReviewFeedbackItem(target_id="node_01", feedback_type="challenge", text="Disagree with direction"),
                ReviewFeedbackItem(feedback_type="signoff", text="Overall LGTM"),
            ],
            completed_at=FIXED_DT,
        ),
        "dataset_version_library_empty": DatasetVersionLibrary(),
        "dataset_version_library_populated": DatasetVersionLibrary(
            entries=[
                DatasetVersion(
                    id=new_id("data-version"),
                    dataset_id="dataset_01EXAMPLE",
                    name="raw-import",
                    description="As-uploaded before any cleaning",
                    commit_sha="c" * 40,
                    content_hash="sha256:abc123",
                    row_count=1200,
                    column_count=5,
                    column_names=["date", "price", "volume", "region", "source"],
                    created_by=ALICE,
                ),
                DatasetVersion(
                    id=new_id("data-version"),
                    dataset_id="dataset_01EXAMPLE",
                    name="cleaned-v1",
                    commit_sha="d" * 40,
                    content_hash="sha256:def456",
                    row_count=1153,
                    column_count=4,
                    column_names=["date", "price", "volume", "region"],
                    created_by=ALICE,
                ),
            ]
        ),
    }


@pytest.mark.parametrize("fixture_name", list(_fixtures().keys()))
def test_byte_identical_round_trip(tmp_path: Path, fixture_name: str) -> None:
    model = _fixtures()[fixture_name]
    path1 = tmp_path / f"{fixture_name}.yaml"
    path2 = tmp_path / f"{fixture_name}.2.yaml"

    dump_model(model, path1)
    bytes_first = path1.read_bytes()

    loaded = load_model(type(model), path1)
    dump_model(loaded, path2)
    bytes_second = path2.read_bytes()

    assert bytes_first == bytes_second, (
        f"round-trip drift for {fixture_name}:\n"
        f"--- first ---\n{bytes_first.decode('utf-8')}\n"
        f"--- second ---\n{bytes_second.decode('utf-8')}"
    )


@pytest.mark.parametrize("fixture_name", list(_fixtures().keys()))
def test_load_reconstructs_equal_model(tmp_path: Path, fixture_name: str) -> None:
    model = _fixtures()[fixture_name]
    path = tmp_path / f"{fixture_name}.yaml"
    dump_model(model, path)
    loaded = load_model(type(model), path)
    assert loaded == model


def test_lineage_node_backward_compat_without_archived(tmp_path: Path) -> None:
    """A lineage-node.yaml written before the archived/superseded_by fields
    existed must still load, defaulting archived=False, superseded_by=None."""
    path = tmp_path / "old-lineage-node.yaml"
    path.write_text(
        "id: version_01OLD\n"
        "name: Pre-archived version\n"
        "maturity: proposed\n"
        "relationship: original\n"
        "created_by:\n"
        "  name: Alice\n"
        "  email: alice@example.com\n",
        encoding="utf-8",
    )
    loaded = load_model(LineageNode, path)
    assert loaded.archived is False
    assert loaded.superseded_by is None
