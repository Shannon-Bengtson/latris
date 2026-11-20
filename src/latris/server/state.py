"""Load full project state from disk into a single JSON-serialisable dict.

The GUI hydrates its zustand store from this endpoint on connect.  Each
section loads only if its file exists — a freshly initialised project has
empty lists for most sections.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from latris.operations.references import load_library as load_ref_library
from latris.perf import span
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import iter_jsonl, load_model, load_model_or_default
from latris.schema import (
    AssumptionLog,
    ChallengeLog,
    ConfidenceSet,
    DataLinkSet,
    DatasetLibrary,
    DatasetVersionLibrary,
    DecisionLog,
    DescriptionSet,
    EvidenceLinkSet,
    ExclusionLog,
    FloatSet,
    LineageNode,
    MappingRegistry,
    MilestoneLog,
    PolaritySet,
    PredictionLog,
    ProjectFoundation,
    QuestionLog,
    SessionLog,
    SignoffLog,
    Substrate,
)
from latris.schema.findings import Finding
from latris.schema.interpretation import InterpretationStore
from latris.schema.provenance import ModelChoiceLog
from latris.schema.references import ReferenceLibrary
from latris.schema.review import ReviewSessionLog

# ── The state's shape: typed, so the API types the app is built against carry every entity ─────────────


class AttributeState(BaseModel):
    descriptions: DescriptionSet
    confidence: ConfidenceSet
    evidence: EvidenceLinkSet
    data_links: DataLinkSet


class CldAttributes(BaseModel):
    polarity: PolaritySet


class FcmAttributes(BaseModel):
    weight: FloatSet


class ViewAttributeState(BaseModel):
    cld: CldAttributes
    fcm: FcmAttributes


class ProvenanceState(BaseModel):
    assumptions: AssumptionLog
    decisions: DecisionLog
    model_choices: ModelChoiceLog
    signoffs: SignoffLog
    sessions: SessionLog
    questions: QuestionLog
    exclusions: ExclusionLog
    predictions: PredictionLog
    review_sessions: ReviewSessionLog


class LineageState(BaseModel):
    current_node: LineageNode | None
    milestones: MilestoneLog
    current_branch: str


class ProjectState(BaseModel):
    """Everything the app hydrates from, in one read (``GET /api/state``)."""

    project: ProjectFoundation
    substrate: Substrate
    references: ReferenceLibrary
    challenges: ChallengeLog
    mappings: MappingRegistry
    attributes: AttributeState
    view_attributes: ViewAttributeState
    provenance: ProvenanceState
    findings: list[Finding]
    interpretation: InterpretationStore
    datasets: DatasetLibrary
    versions: DatasetVersionLibrary
    lineage: LineageState


def load_full_state(paths: ProjectPaths) -> dict[str, Any]:
    """Return the entire project state as a JSON-serialisable dict."""
    return load_project_state(paths).model_dump(mode="json")


def load_project_state(paths: ProjectPaths) -> ProjectState:
    """The entire project state, typed."""
    with span("load_full_state"):
        return _load_full_state(paths)


def _load_full_state(paths: ProjectPaths) -> ProjectState:
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ref_library, _ = load_ref_library(paths)
    challenges = load_model(ChallengeLog, paths.challenges_yaml)
    mappings = load_model(MappingRegistry, paths.mappings_yaml)

    descriptions = load_model(DescriptionSet, paths.descriptions_yaml)
    confidence = load_model(ConfidenceSet, paths.confidence_yaml)
    polarity_path = paths.view_attribute_path("cld", "polarity")
    polarity = load_model_or_default(PolaritySet, polarity_path)
    fcm_weight_path = paths.view_attribute_path("fcm", "weight")
    fcm_weight = load_model_or_default(FloatSet, fcm_weight_path)
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    data_links = load_model_or_default(DataLinkSet, paths.data_links_yaml)

    assumptions = load_model(AssumptionLog, paths.assumptions_yaml)
    decisions = load_model(DecisionLog, paths.decisions_yaml)
    model_choices = (
        load_model(ModelChoiceLog, paths.model_choices_yaml)
        if paths.model_choices_yaml.exists()
        else ModelChoiceLog()
    )
    signoffs = load_model(SignoffLog, paths.signoffs_yaml)
    sessions = load_model(SessionLog, paths.sessions_yaml)
    questions = load_model(QuestionLog, paths.questions_yaml)
    exclusions = load_model(ExclusionLog, paths.exclusions_yaml)
    predictions = load_model(PredictionLog, paths.predictions_yaml)

    review_sessions = (
        load_model(ReviewSessionLog, paths.review_sessions_yaml)
        if paths.review_sessions_yaml.exists()
        else ReviewSessionLog()
    )

    # Datasets and versions.
    datasets = (
        load_model_or_default(DatasetLibrary, paths.data_datasets_yaml)
    )
    versions = (
        load_model(DatasetVersionLibrary, paths.data_versions_yaml)
        if paths.data_versions_yaml.exists()
        else DatasetVersionLibrary()
    )

    # Lineage: current version metadata only (full tree via /api/lineage/tree).
    lineage_node = load_model(LineageNode, paths.lineage_node_yaml) if paths.lineage_node_yaml.exists() else None
    milestone_log = (
        load_model_or_default(MilestoneLog, paths.milestones_yaml)
    )
    try:
        current_branch = git.current_branch(paths.root)
    except git.GitError:
        current_branch = "main"

    # Findings
    findings = list(iter_jsonl(Finding, paths.findings_jsonl))

    # Interpretation
    interpretation = (
        load_model(InterpretationStore, paths.interpretation_yaml)
        if paths.interpretation_yaml.exists() else InterpretationStore()
    )

    return ProjectState(
        project=foundation,
        substrate=substrate,
        references=ref_library,
        challenges=challenges,
        mappings=mappings,
        attributes=AttributeState(
            descriptions=descriptions, confidence=confidence, evidence=evidence, data_links=data_links,
        ),
        view_attributes=ViewAttributeState(
            cld=CldAttributes(polarity=polarity), fcm=FcmAttributes(weight=fcm_weight),
        ),
        provenance=ProvenanceState(
            assumptions=assumptions, decisions=decisions, model_choices=model_choices, signoffs=signoffs,
            sessions=sessions, questions=questions, exclusions=exclusions, predictions=predictions,
            review_sessions=review_sessions,
        ),
        findings=findings,
        interpretation=interpretation,
        datasets=datasets,
        versions=versions,
        lineage=LineageState(current_node=lineage_node, milestones=milestone_log, current_branch=current_branch),
    )
