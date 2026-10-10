"""Load full project state from disk into a single JSON-serialisable dict.

The GUI hydrates its zustand store from this endpoint on connect.  Each
section loads only if its file exists — a freshly initialised project has
empty lists for most sections.
"""

from __future__ import annotations

from typing import Any

from latris.operations.references import load_library as load_ref_library
from latris.perf import span
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import iter_jsonl, load_model
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


def load_full_state(paths: ProjectPaths) -> dict[str, Any]:
    """Return the entire project state as a JSON-serialisable dict."""
    with span("load_full_state"):
        return _load_full_state(paths)


def _load_full_state(paths: ProjectPaths) -> dict[str, Any]:
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    ref_library, _ = load_ref_library(paths)
    challenges = load_model(ChallengeLog, paths.challenges_yaml)
    mappings = load_model(MappingRegistry, paths.mappings_yaml)

    descriptions = load_model(DescriptionSet, paths.descriptions_yaml)
    confidence = load_model(ConfidenceSet, paths.confidence_yaml)
    polarity_path = paths.view_attribute_path("cld", "polarity")
    polarity = load_model(PolaritySet, polarity_path) if polarity_path.exists() else PolaritySet()
    fcm_weight_path = paths.view_attribute_path("fcm", "weight")
    fcm_weight = load_model(FloatSet, fcm_weight_path) if fcm_weight_path.exists() else FloatSet()
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    data_links = load_model(DataLinkSet, paths.data_links_yaml) if paths.data_links_yaml.exists() else DataLinkSet()

    from latris.schema.provenance import ModelChoiceLog

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

    from latris.schema.review import ReviewSessionLog

    review_sessions = (
        load_model(ReviewSessionLog, paths.review_sessions_yaml)
        if paths.review_sessions_yaml.exists()
        else ReviewSessionLog()
    )

    # Datasets and versions.
    datasets = (
        load_model(DatasetLibrary, paths.data_datasets_yaml) if paths.data_datasets_yaml.exists() else DatasetLibrary()
    )
    versions = (
        load_model(DatasetVersionLibrary, paths.data_versions_yaml)
        if paths.data_versions_yaml.exists()
        else DatasetVersionLibrary()
    )

    # Lineage: current version metadata only (full tree via /api/lineage/tree).
    lineage_node = load_model(LineageNode, paths.lineage_node_yaml) if paths.lineage_node_yaml.exists() else None
    milestone_log = (
        load_model(MilestoneLog, paths.milestones_yaml) if paths.milestones_yaml.exists() else MilestoneLog()
    )
    try:
        current_branch = git.current_branch(paths.root)
    except git.GitError:
        current_branch = "main"

    # Findings
    from latris.schema.findings import Finding

    findings = [f.model_dump(mode="json") for f in iter_jsonl(Finding, paths.findings_jsonl)]

    # Interpretation
    from latris.schema.interpretation import InterpretationStore

    if paths.interpretation_yaml.exists():
        interpretation = load_model(InterpretationStore, paths.interpretation_yaml).model_dump(mode="json")
    else:
        interpretation = {"sections": []}

    return {
        "project": foundation.model_dump(mode="json"),
        "substrate": substrate.model_dump(mode="json"),
        "references": ref_library.model_dump(mode="json"),
        "challenges": challenges.model_dump(mode="json"),
        "mappings": mappings.model_dump(mode="json"),
        "attributes": {
            "descriptions": descriptions.model_dump(mode="json"),
            "confidence": confidence.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "data_links": data_links.model_dump(mode="json"),
        },
        "view_attributes": {
            "cld": {
                "polarity": polarity.model_dump(mode="json"),
            },
            "fcm": {
                "weight": fcm_weight.model_dump(mode="json"),
            },
        },
        "provenance": {
            "assumptions": assumptions.model_dump(mode="json"),
            "decisions": decisions.model_dump(mode="json"),
            "model_choices": model_choices.model_dump(mode="json"),
            "signoffs": signoffs.model_dump(mode="json"),
            "sessions": sessions.model_dump(mode="json"),
            "questions": questions.model_dump(mode="json"),
            "exclusions": exclusions.model_dump(mode="json"),
            "predictions": predictions.model_dump(mode="json"),
            "review_sessions": review_sessions.model_dump(mode="json"),
        },
        "findings": findings,
        "interpretation": interpretation,
        "datasets": datasets.model_dump(mode="json"),
        "versions": versions.model_dump(mode="json"),
        "lineage": {
            "current_node": lineage_node.model_dump(mode="json") if lineage_node else None,
            "milestones": milestone_log.model_dump(mode="json"),
            "current_branch": current_branch,
        },
    }
