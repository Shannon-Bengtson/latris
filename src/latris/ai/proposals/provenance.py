"""Proposals of provenance records: assumptions, decisions, exclusions, questions."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import DecisionEntry, DraftAssumption, ExclusionEntry, QuestionEntry, _Base
from latris.operations.provenance import add_assumption, add_exclusion, add_question, log_decision
from latris.repo.layout import ProjectPaths


class AssumptionsProposal(_Base):
    """GenerateAssumptions output. Proposed assumptions for an element."""

    target_id: str = Field(..., description="Element these assumptions pertain to.")
    assumptions: list[DraftAssumption] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        created_ids: list[str] = []
        for a in self.assumptions:
            entry, _ = add_assumption(
                a.statement,
                rationale=a.rationale or None,
                target_id=self.target_id,
                root=paths.root,
            )
            created_ids.append(entry.id)
        return created_ids


class DecisionsProposal(_Base):
    """SuggestDecisions output. Proposed modelling decisions for an element."""

    target_id: str = Field(..., description="Element these decisions pertain to.")
    decisions: list[DecisionEntry] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        created_ids: list[str] = []
        for d in self.decisions:
            entry, _ = log_decision(
                d.statement,
                d.rationale,
                target_id=self.target_id,
                root=paths.root,
            )
            created_ids.append(entry.id)
        return created_ids


class ExclusionsProposal(_Base):
    """SuggestExclusions output. Proposed scope exclusions for the model."""

    exclusions: list[ExclusionEntry] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        created_ids: list[str] = []
        for e in self.exclusions:
            entry, _ = add_exclusion(
                e.statement,
                e.rationale,
                root=paths.root,
            )
            created_ids.append(entry.id)
        return created_ids


class QuestionsProposal(_Base):
    """RaiseQuestions output. Proposed open questions for an element."""

    target_id: str = Field(..., description="Element these questions pertain to.")
    questions: list[QuestionEntry] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        created_ids: list[str] = []
        for q in self.questions:
            entry, _ = add_question(
                q.question,
                target_id=self.target_id,
                root=paths.root,
            )
            created_ids.append(entry.id)
        return created_ids
