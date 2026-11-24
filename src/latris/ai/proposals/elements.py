"""Proposals and results about one element: explain it, challenge it, cite it, argue the other side, fill a field."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import CitationSuggestion, ProvenanceBundle, _apply_provenance_bundle, _Base
from latris.operations.challenges import add_turn, open_challenge
from latris.operations.evidence import add_evidence
from latris.operations.references import add_reference, list_references
from latris.repo.layout import ProjectPaths
from latris.schema.ai import ChallengeState


class ChallengeProposal(_Base):
    """A proposed challenge against a target. Maps to `open_challenge`."""

    target_id: str = Field(..., description="Node or edge ID being challenged.")
    target_attribute: str | None = Field(
        None,
        description="Specific attribute under challenge (e.g. 'polarity'). Optional.",
    )
    argument: str = Field(..., description="The core argument against the target.")
    opening_turn: str | None = Field(
        None,
        description="Optional first conversation turn expanding on the argument.",
    )
    recommended_state: ChallengeState | None = Field(
        None,
        description="Advisory — suggested terminal state if the human agrees. NOT applied automatically.",
    )
    provenance: ProvenanceBundle = Field(default_factory=ProvenanceBundle)

    def apply(self, paths: ProjectPaths) -> list[str]:
        challenge, _ = open_challenge(
            self.target_id,
            self.argument,
            attribute=self.target_attribute,
            root=paths.root,
        )
        if self.opening_turn:
            add_turn(challenge.id, self.opening_turn, root=paths.root)
        created_ids = [challenge.id]
        created_ids.extend(_apply_provenance_bundle(self.provenance, self.target_id, paths))
        return created_ids


class EvidenceAttachment(_Base):
    """A proposed evidence link. Bibkey must either exist or appear in new_references."""

    target_id: str
    attribute: str
    bibkey: str
    rationale: str


class CitationsProposal(_Base):
    """Output of SuggestCitations.

    Safety rail: every ``evidence_links[i].bibkey`` MUST be either in the
    project's existing reference library or in ``new_references``. Apply
    enforces this; AI fabrications never land.
    """

    new_references: list[CitationSuggestion] = Field(default_factory=list)
    evidence_links: list[EvidenceAttachment] = Field(default_factory=list)
    provenance: ProvenanceBundle = Field(default_factory=ProvenanceBundle)

    def apply(self, paths: ProjectPaths) -> list[str]:
        known_bibkeys = {r.bibkey for r in list_references(paths.root)}
        new_bibkeys = {r.bibkey for r in self.new_references}

        # Safety rail: refuse to apply evidence links whose bibkeys aren't accounted for.
        unresolved = [e for e in self.evidence_links if e.bibkey not in known_bibkeys and e.bibkey not in new_bibkeys]
        if unresolved:
            bibs = ", ".join(sorted({e.bibkey for e in unresolved}))
            raise ValueError(
                f"refusing to apply: evidence_links reference bibkeys "
                f"({bibs}) that are neither in the reference library nor "
                "in this proposal's new_references (AI fabrication guard)."
            )

        created_ids: list[str] = []

        # Add new references first, skipping ones that already exist (the AI's
        # `already_in_library` is advisory; we trust the actual library).
        for ref in self.new_references:
            if ref.bibkey in known_bibkeys:
                continue
            added, _ = add_reference(
                ref.bibkey,
                ref.title,
                authors=ref.authors,
                year=ref.year,
                doi=ref.doi,
                url=ref.url,
                root=paths.root,
            )
            created_ids.append(added.bibkey)

        # Then attach evidence.
        for link in self.evidence_links:
            attached, _ = add_evidence(
                link.target_id,
                link.attribute,
                link.bibkey,
                verified_by="ai",
                notes=link.rationale,
                root=paths.root,
            )
            created_ids.append(f"{attached.target_id}/{attached.attribute}@{attached.bibkey}")

        # Apply bundled provenance (target_id from first evidence link, or None).
        target = self.evidence_links[0].target_id if self.evidence_links else None
        created_ids.extend(_apply_provenance_bundle(self.provenance, target, paths))
        return created_ids


class SteelmanProposal(_Base):
    """SteelmanOpposingView output. Adds a contested-view annotation."""

    target_id: str = Field(..., description="Element whose opposing framing we steelmanned.")
    opposing_view: str = Field(..., description="The steelmanned counter-framing.")
    rationale: str = Field("", description="Why this is the strongest version of the opposition.")
    provenance: ProvenanceBundle = Field(default_factory=ProvenanceBundle)

    def apply(self, paths: ProjectPaths) -> list[str]:
        from latris.operations.attributes import add_contested_view

        target_id, _sha = add_contested_view(
            self.target_id,
            self.opposing_view,
            root=paths.root,
        )
        created_ids = [target_id]
        created_ids.extend(_apply_provenance_bundle(self.provenance, self.target_id, paths))
        return created_ids


class ExplanationResult(_Base):
    """ExplainThisElement output. No ``apply()`` — logged, never commits."""

    explanation: str = Field(..., description="Plain-prose explanation of the element.")
    referenced_ids: list[str] = Field(
        default_factory=list,
        description="Other node/edge IDs the explanation refers to.",
    )


class FillFieldProposal(_Base):
    """FillProvenanceField output.

    Read-only from the AI orchestrator's perspective: the GUI inserts
    ``value`` into the editable field, and the user's normal save action
    commits via the existing per-field mutation path. Nothing here calls
    ``apply()`` — the suggestion does not mutate the substrate on its own.
    """

    value: str = Field(..., description="The suggested field value.")
    rationale: str = Field(
        "",
        description=(
            "One-sentence reasoning for the suggestion — visible to the "
            "user as a tooltip or expandable note."
        ),
    )
    confidence: str = Field(
        "medium", description="low | medium | high — calibrate the user's review effort."
    )
