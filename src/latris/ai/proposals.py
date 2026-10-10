"""Structured proposal schemas + apply() dispatchers.

Every prompt that mutates the substrate returns a pydantic ``*Proposal``.
``apply(paths)`` is the *only* way a proposal becomes a commit; it delegates
to existing ``operations/*`` so the same auto-commit + identity-guard path
is used whether the caller was a human or the AI. No proposal bypasses
``operations/``.

Prompts that are read-only (e.g. ExplainThisElement) return a
``*Result`` model with no ``apply()`` — the orchestrator logs them and
stops.
"""

from __future__ import annotations

from contextlib import nullcontext

from pydantic import BaseModel, ConfigDict, Field

from latris.operations.attributes import set_attribute
from latris.operations.batch import batch, get_active_batch
from latris.operations.challenges import add_turn, open_challenge
from latris.operations.edges import add_edge, remove_edge, retype_edge
from latris.operations.evidence import (
    add_evidence,
    remove_evidence,
    set_evidence_support_verdict,
)
from latris.operations.nodes import add_node, list_nodes
from latris.operations.provenance import (
    add_assumption,
    add_exclusion,
    add_question,
    log_decision,
)
from latris.operations.references import add_reference, list_references
from latris.operations.view_attributes import set_view_attribute
from latris.repo.layout import ProjectPaths
from latris.schema.ai import ChallengeState
from latris.schema.substrate import (
    EntityKind,
    coerce_edge_kind,
    coerce_entity_kind,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)




class ProvenanceBundle(_Base):
    """Optional provenance entries bundled with a mutation proposal.

    LLM-generated assumptions and questions that accompany the main
    proposal content. Defaults to empty (backwards compatible).
    """

    assumptions: list[DraftAssumption] = Field(default_factory=list)
    questions: list[QuestionEntry] = Field(default_factory=list)


def _apply_provenance_bundle(
    bundle: ProvenanceBundle,
    target_id: str | None,
    paths: ProjectPaths,
) -> list[str]:
    """Apply bundled provenance entries, returning created IDs."""
    created: list[str] = []
    for a in bundle.assumptions:
        entry, _ = add_assumption(
            a.statement,
            rationale=a.rationale or None,
            target_id=target_id,
            root=paths.root,
        )
        created.append(entry.id)
    for q in bundle.questions:
        entry, _ = add_question(
            q.question,
            target_id=target_id,
            root=paths.root,
        )
        created.append(entry.id)
    return created


_VALID_CONFIDENCE = {"low", "medium", "high", "quantitative-pending"}


def _grouped_commit(paths: ProjectPaths, subject: str):
    """Collapse an apply()'s many writes into one commit — unless a batch is
    already active (nesting is unsupported), in which case defer to it."""
    if get_active_batch() is not None:
        return nullcontext()
    return batch(paths.root, subject=subject)


def _cld_selected(paths: ProjectPaths) -> bool:
    """True when the project has the CLD model type selected — the gate for
    persisting co-authored edge polarity (a CLD view attribute)."""
    from latris.operations.project import load_foundation

    try:
        _, foundation = load_foundation(paths.root)
    except Exception:
        return False
    return "cld" in set(foundation.selected_model_types or [])


def _bind_entity_provenance(
    *,
    target_id: str,
    assumptions: list[DraftAssumption],
    source_bibkeys: list[str],
    confidence: str | None,
    known_bibkeys: set[str],
    paths: ProjectPaths,
) -> list[str]:
    """Bind a created node/edge's endogenous/already-grounded provenance to it:
    assumptions → assumption entries on ``target_id``; ``source_bibkeys`` →
    ``existence`` evidence links (only for bibkeys actually in the library —
    a fabricated one is skipped, never invented); confidence → attribute.
    Returns the created assumption IDs."""
    created: list[str] = []
    for a in assumptions:
        entry, _ = add_assumption(
            a.statement, rationale=a.rationale or None, target_id=target_id, root=paths.root
        )
        created.append(entry.id)
    for bibkey in source_bibkeys:
        if bibkey in known_bibkeys:
            add_evidence(target_id, "existence", bibkey, verified_by="ai", root=paths.root)
    if confidence and confidence.strip().lower() in _VALID_CONFIDENCE:
        # Non-destructive: don't clobber an existing confidence on a reused node.
        set_attribute(
            target_id, "confidence", confidence.strip().lower(), preserve_existing=True, root=paths.root
        )
    return created


def _persist_edge_polarity(
    edge_id: str,
    polarity: str | None,
    rationale: str,
    is_cld: bool,
    paths: ProjectPaths,
) -> None:
    """Persist a co-authored edge polarity + its rationale to the CLD view
    store, in the same act that created the edge — so description, polarity, and
    rationale come from one reasoning pass and stay coherent. No-op unless CLD is
    selected and the polarity is a recognised value."""
    if not (is_cld and polarity):
        return
    value = polarity.strip()
    if value not in ("+", "-", "~"):
        return
    # Non-destructive: co-authored polarity never clobbers a prior value (and is
    # itself never clobbered by a later SuggestEdgePolarities pass). A brand-new
    # edge has none, so this still writes at creation time.
    set_view_attribute(
        edge_id,
        "cld",
        "polarity",
        value,
        rationale=(rationale.strip() or None),
        preserve_existing=True,
        root=paths.root,
    )


def _record_value_conflict(
    target_id: str,
    attribute: str,
    suggested: str,
    existing: str,
    rationale: str,
    paths: ProjectPaths,
) -> str | None:
    """An AI value-set call disagreed with an existing unique-attribute value.
    We never overwrite; instead log a question on the element so a human can
    reconcile — the disagreement is captured, not silently dropped."""
    msg = f"AI suggests {attribute} '{suggested}' but this element is set to '{existing}'."
    if rationale.strip():
        msg += f" Rationale: {rationale.strip()}"
    entry, _ = add_question(msg, target_id=target_id, root=paths.root)
    return entry.id


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


class CitationSuggestion(_Base):
    """A candidate reference. Either already in the library or net-new."""

    bibkey: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    already_in_library: bool = Field(
        default=False,
        description="AI's claim. We verify against the actual library before applying.",
    )
    url_verified: bool = Field(
        default=False,
        description="Whether the URL/DOI was verified to resolve. Set server-side.",
    )


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


# ---------- M12 proposals ----------


class DraftAssumption(_Base):
    """An assumption underlying a framing or a specific entity."""

    statement: str = Field(..., description="The assumption being made.")
    rationale: str = Field("", description="Why this assumption is necessary.")
    target_label: str | None = Field(None, description="Entity label this assumption pertains to, if any.")


# Every draft node/edge schema below carries the same optional provenance trio
# so it is captured in the same call that proposes the structural edit:
# assumptions bind to the created element, source_bibkeys become evidence links,
# confidence rides along. All default-empty — the model fills them only where
# warranted (see the _ENTITY_PROVENANCE_GUIDANCE rubric); un-migrated callers
# and existing fixtures are unaffected.
_ASSUMPTIONS_DESC = (
    "Assumptions this element rests on — only where non-obvious; "
    "do not manufacture one per element."
)
_SOURCE_BIBKEYS_DESC = (
    "Bibkeys of supplied references this element is grounded in "
    "(must be present in the supplied evidence; never invent one)."
)
_CONFIDENCE_DESC = "Confidence in this element: low / medium / high."


class DraftEntity(_Base):
    """A proposed entity within a DraftConceptualModel framing."""

    label: str
    # Typed as EntityKind (like ExtractedVariable/SuggestedVariable) so the
    # structured-output layer constrains the kind to the valid set and the
    # model can't silently default everything to 'concept'. Serialises to a
    # plain string, so GUI consumers are unaffected.
    kind: EntityKind = Field("concept", description="Entity kind; follow the NODE KIND rubric in the prompt.")
    description: str = Field("", description="What this entity represents and why it matters.")
    assumptions: list[DraftAssumption] = Field(default_factory=list, description=_ASSUMPTIONS_DESC)
    confidence: str | None = Field(None, description=_CONFIDENCE_DESC)
    source_bibkeys: list[str] = Field(default_factory=list, description=_SOURCE_BIBKEYS_DESC)


class DraftEdge(_Base):
    """A proposed edge within a DraftConceptualModel framing."""

    from_label: str
    to_label: str
    kind: str = "causal"
    polarity: str | None = None
    polarity_rationale: str = Field("", description="Causal story for the polarity; must match the description.")
    description: str = Field("", description="The mechanism or rationale for this connection.")
    assumptions: list[DraftAssumption] = Field(default_factory=list, description=_ASSUMPTIONS_DESC)
    confidence: str | None = Field(None, description=_CONFIDENCE_DESC)
    source_bibkeys: list[str] = Field(default_factory=list, description=_SOURCE_BIBKEYS_DESC)


class DraftFraming(_Base):
    """One candidate framing — a set of entities and edges."""

    name: str = Field(..., description="Short name for this framing.")
    entities: list[DraftEntity] = Field(default_factory=list)
    edges: list[DraftEdge] = Field(default_factory=list)
    assumptions: list[DraftAssumption] = Field(default_factory=list)
    rationale: str = ""


class DraftModelProposal(_Base):
    """Output of DraftConceptualModel. Multiple framings; user picks one."""

    framings: list[DraftFraming] = Field(default_factory=list)
    selected_index: int | None = Field(
        None,
        description="Set by the CLI after the user picks a framing. apply() uses this.",
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        if self.selected_index is None:
            raise ValueError("No framing selected. Set selected_index before apply().")
        if self.selected_index < 0 or self.selected_index >= len(self.framings):
            raise ValueError(f"selected_index {self.selected_index} out of range (0-{len(self.framings) - 1}).")
        framing = self.framings[self.selected_index]
        created_ids: list[str] = []
        known_bibkeys = {r.bibkey for r in list_references(paths.root)}
        is_cld = _cld_selected(paths)

        def _norm(s: str) -> str:
            return " ".join(s.split()).lower()

        # One commit for the whole framing rather than one per node/edge/
        # assumption/evidence write (see operations/batch.py).
        with _grouped_commit(paths, f"Draft model: {framing.name}"):
            # Create nodes first so edges can reference them. Dedup is
            # case/whitespace-insensitive so near-duplicate labels ("Phosphorus
            # load" vs "phosphorus  load") collapse onto one node rather than
            # spawning parallels — a common source of run-to-run inconsistency.
            label_to_id: dict[str, str] = {}
            norm_to_id: dict[str, str] = {}
            existing = list_nodes(paths.root)
            for e in existing:
                label_to_id[e.label] = e.id
                norm_to_id[_norm(e.label)] = e.id

            for ent in framing.entities:
                norm = _norm(ent.label)
                existing_id = norm_to_id.get(norm)
                if existing_id is not None:
                    node_id = existing_id
                    label_to_id[ent.label] = existing_id
                else:
                    kind, _ = coerce_entity_kind(ent.kind)
                    node, _ = add_node(ent.label, kind=kind, root=paths.root)
                    node_id = node.id
                    label_to_id[ent.label] = node_id
                    norm_to_id[norm] = node_id
                    created_ids.append(node_id)
                    if ent.description:
                        set_attribute(node_id, "description", ent.description, root=paths.root)
                # Provenance binds to the resolved node whether new or reused.
                created_ids.extend(
                    _bind_entity_provenance(
                        target_id=node_id,
                        assumptions=ent.assumptions,
                        source_bibkeys=ent.source_bibkeys,
                        confidence=ent.confidence,
                        known_bibkeys=known_bibkeys,
                        paths=paths,
                    )
                )

            for edg in framing.edges:
                from_id = label_to_id.get(edg.from_label) or norm_to_id.get(_norm(edg.from_label))
                to_id = label_to_id.get(edg.to_label) or norm_to_id.get(_norm(edg.to_label))
                if from_id is None or to_id is None:
                    continue  # skip edges referencing unknown labels
                edge_kind, _ = coerce_edge_kind(edg.kind)
                edge, _ = add_edge(from_id, to_id, kind=edge_kind, root=paths.root)
                created_ids.append(edge.id)
                if edg.description:
                    set_attribute(edge.id, "description", edg.description, root=paths.root)
                _persist_edge_polarity(edge.id, edg.polarity, edg.polarity_rationale, is_cld, paths)
                created_ids.extend(
                    _bind_entity_provenance(
                        target_id=edge.id,
                        assumptions=edg.assumptions,
                        source_bibkeys=edg.source_bibkeys,
                        confidence=edg.confidence,
                        known_bibkeys=known_bibkeys,
                        paths=paths,
                    )
                )

            # Framing-level assumptions that name a node bind to it; the rest
            # are model-level. (Per-entity assumptions are handled above.)
            for assumption in framing.assumptions:
                target_id = label_to_id.get(assumption.target_label) if assumption.target_label else None
                entry, _ = add_assumption(
                    assumption.statement,
                    rationale=assumption.rationale or None,
                    target_id=target_id,
                    root=paths.root,
                )
                created_ids.append(entry.id)

        return created_ids


class EdgeProposal(_Base):
    """A single proposed edge between existing nodes."""

    from_id: str
    to_id: str
    kind: str = "causal"
    rationale: str = ""
    description: str = Field("", description="The mechanism or rationale for this connection.")
    polarity: str | None = None
    polarity_rationale: str = Field("", description="Causal story for the polarity; must match the description.")
    assumptions: list[DraftAssumption] = Field(default_factory=list, description=_ASSUMPTIONS_DESC)
    confidence: str | None = Field(None, description=_CONFIDENCE_DESC)
    source_bibkeys: list[str] = Field(default_factory=list, description=_SOURCE_BIBKEYS_DESC)


class NewConnectionsProposal(_Base):
    """Output of FindNewConnections. Proposed edges between existing nodes."""

    proposals: list[EdgeProposal] = Field(default_factory=list)
    approved_indices: list[int] | None = Field(
        None,
        description="Set by the CLI after user selects which proposals to apply.",
    )
    provenance: ProvenanceBundle = Field(default_factory=ProvenanceBundle)

    def apply(self, paths: ProjectPaths) -> list[str]:
        if self.approved_indices is None:
            raise ValueError("No proposals approved. Set approved_indices before apply().")
        created_ids: list[str] = []
        known_bibkeys = {r.bibkey for r in list_references(paths.root)}
        is_cld = _cld_selected(paths)
        with _grouped_commit(paths, "Add connections"):
            for i in self.approved_indices:
                if i < 0 or i >= len(self.proposals):
                    continue
                p = self.proposals[i]
                edge, _ = add_edge(p.from_id, p.to_id, kind=p.kind, root=paths.root)
                created_ids.append(edge.id)
                desc = p.description or p.rationale
                if desc:
                    set_attribute(edge.id, "description", desc, root=paths.root)
                _persist_edge_polarity(edge.id, p.polarity, p.polarity_rationale, is_cld, paths)
                # Bind provenance to THIS edge (fixes the old target_id=None dump
                # that left assumptions unbound to the edge they justify).
                created_ids.extend(
                    _bind_entity_provenance(
                        target_id=edge.id,
                        assumptions=p.assumptions,
                        source_bibkeys=p.source_bibkeys,
                        confidence=p.confidence,
                        known_bibkeys=known_bibkeys,
                        paths=paths,
                    )
                )
            # The proposal-level bundle carries genuinely MODEL-level provenance
            # (target=None) — assumptions/questions about the batch as a whole.
            # Per-edge provenance is bound to its edge above; this is additive.
            created_ids.extend(_apply_provenance_bundle(self.provenance, None, paths))
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


# ---------- Provenance-generating proposals ----------


class DecisionEntry(_Base):
    """A single proposed modelling decision."""

    statement: str = Field(..., description="The modelling decision statement.")
    rationale: str = Field(..., description="Why this decision was made.")
    target_label: str | None = Field(
        None,
        description="Entity label this decision pertains to, if any.",
    )


class ExclusionEntry(_Base):
    """A single proposed scope exclusion."""

    statement: str = Field(..., description="What is excluded from scope.")
    rationale: str = Field(..., description="Why it is excluded.")


class QuestionEntry(_Base):
    """A single proposed open question."""

    question: str = Field(..., description="The open question to park.")


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


# ---------- Read-only results ----------


class ExplanationResult(_Base):
    """ExplainThisElement output. No ``apply()`` — logged, never commits."""

    explanation: str = Field(..., description="Plain-prose explanation of the element.")
    referenced_ids: list[str] = Field(
        default_factory=list,
        description="Other node/edge IDs the explanation refers to.",
    )


class AttackResult(_Base):
    """AttackThisModel output — hybrid prose + bounded mutation.

    The prose fields (``argument``, ``recommended_action``) are the
    user-facing critique that always renders into the report. The
    structured fields convert the named weakest assumption into a
    formal ``Assumption(contested=True)`` record plus a single
    follow-up ``OpenQuestion``, both committed via the standard
    proposal/approve/apply pathway.

    Bounded-mutation principle: at most 1 assumption + 1 question per
    attack. The point is to convert critical observations into
    trackable provenance records, not to flood the project.
    """

    weakest_assumption: str = Field(..., description="The assumption most likely to be wrong.")
    argument: str = Field(..., description="Why this assumption is the weakest.")
    affected_node_ids: list[str] = Field(
        default_factory=list,
        description="Nodes whose conclusions depend on this assumption.",
    )
    recommended_action: str | None = Field(
        None,
        description="What the modeller should do about it.",
    )
    record_assumption: bool = Field(
        True,
        description=(
            "Whether to formalise the named weakest assumption as a "
            "contested Assumption record. Default True. Set False when "
            "the AI judges the attack to be exploratory rather than "
            "load-bearing."
        ),
    )
    follow_up_question: str | None = Field(
        None,
        description=(
            "Optional one-line follow-up question to track. Phrased as "
            "something a reviewer could discharge: e.g. 'Does X actually "
            "hold for our small-firm context?'"
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        created: list[str] = []
        # Bound the mutation: at most one assumption record per attack.
        if self.record_assumption and self.weakest_assumption.strip():
            target_id = self.affected_node_ids[0] if self.affected_node_ids else None
            entry, _ = add_assumption(
                self.weakest_assumption,
                rationale=f"Surfaced by AttackThisModel: {self.argument}",
                target_id=target_id,
                root=paths.root,
            )
            created.append(entry.id)
        if self.follow_up_question and self.follow_up_question.strip():
            target_id = self.affected_node_ids[0] if self.affected_node_ids else None
            entry, _ = add_question(
                self.follow_up_question,
                target_id=target_id,
                root=paths.root,
            )
            created.append(entry.id)
        return created


class ProposedEdgeSketch(_Base):
    """A from→to edge hint produced by FindCounterPathway.

    Advisory only — these are NOT applied as real edges. The human
    reviewer reads the sketch in the report prose and decides whether to
    materialise the counter-pathway via the normal edge-add workflow.
    """

    from_label: str = Field(..., description="Source node label.")
    to_label: str = Field(..., description="Target node label.")
    polarity: str = Field("+", description="Edge polarity: '+', '-', or '~'.")
    rationale: str = Field("", description="One-sentence mechanism for this edge.")


class CounterPathwayResult(_Base):
    """FindCounterPathway output — prose + bounded mutation.

    Names the strongest *missing* causal pathway and sketches it as a
    list of (from, to, polarity) hints, but does NOT auto-create
    entities or edges — the pathway is advisory until the human reviewer
    materialises it. The bounded mutation is at most one tracked Open
    Question naming the missing mechanism.

    Mirrors AttackResult's hybrid shape: prose for the report, structured
    fields for provenance. AttackThisModel attacks an *assumption*; this
    prompt attacks the *structure* by naming a pathway that, if drawn,
    would weaken the headline conclusion.
    """

    missing_mechanism: str = Field(
        ...,
        description="Short name (1-4 words) for the missing counter-pathway.",
    )
    argument: str = Field(
        ...,
        description="Why adding this pathway would weaken the headline conclusion.",
    )
    proposed_nodes: list[str] = Field(
        default_factory=list,
        description="Node labels that would represent the mechanism, if not present.",
    )
    proposed_edges: list[ProposedEdgeSketch] = Field(
        default_factory=list,
        description="Edges that would sketch the counter-pathway. Advisory only.",
    )
    supporting_bibkey: str | None = Field(
        None,
        description="Most relevant reference for the mechanism, or null.",
    )
    record_question: bool = Field(
        True,
        description=(
            "Whether to formalise the missing mechanism as a tracked open "
            "question. Default True. Set False when the pathway is "
            "speculative and not worth tracking."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        if not (self.record_question and self.missing_mechanism.strip()):
            return []
        question = (
            f"Counter-pathway not represented: '{self.missing_mechanism}'. "
            f"{self.argument}"
        )
        entry, _ = add_question(question, root=paths.root)
        return [entry.id]


class ScopeCheckResult(_Base):
    """ScopeCheck output — hybrid prose + bounded mutation.

    The prose (``verdict``, ``reasoning``, ``suggestions``) renders into
    the report. The structured ``proposed_exclusions`` and
    ``proposed_questions`` are committed as formal records. The AI
    populates exclusions when verdict=``too-broad`` (something is in
    scope that probably shouldn't be) and questions when verdict=
    ``too-narrow`` (something is out of scope that maybe should be).

    Bounded-mutation principle: keep proposals to a small handful;
    don't flood the audit trail.
    """

    verdict: str = Field(..., description="too-narrow | too-broad | well-matched")
    suggestions: list[str] = Field(default_factory=list, description="Proposed scope adjustments.")
    reasoning: str = Field("", description="Why this verdict.")
    proposed_exclusions: list[ExclusionEntry] = Field(
        default_factory=list,
        description=(
            "Concrete exclusions to record (use when verdict=too-broad). "
            "Each is an explicit boundary statement that will be tracked "
            "as project provenance."
        ),
    )
    proposed_questions: list[QuestionEntry] = Field(
        default_factory=list,
        description=(
            "Concrete questions to log (use when verdict=too-narrow). "
            "Each is a discharge-able question about whether to bring "
            "something into scope."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        created: list[str] = []
        for e in self.proposed_exclusions:
            entry, _ = add_exclusion(
                e.statement,
                e.rationale,
                root=paths.root,
            )
            created.append(entry.id)
        for q in self.proposed_questions:
            entry, _ = add_question(
                q.question,
                root=paths.root,
            )
            created.append(entry.id)
        return created


class ElicitationTurnResult(_Base):
    """RunElicitationInterview output. Read-only — a question for the expert."""

    question: str = Field(..., description="The next question to ask the expert.")
    proposed_edit: dict | None = Field(
        None,
        description="Optional structured suggestion if the expert's answer resolves an attribute.",
    )


class ReportSection(_Base):
    """One section of a generated report pack.

    Bounded-content design: a runaway emission in one section's markdown
    fails that section's parse, not the whole report. Heading is plain
    text (no leading '##' — consumers prefix at render time).
    """

    heading: str = Field(..., description="Section heading text, without leading markdown #.")
    content: str = Field(..., description="Markdown content for this section.")


class ReportDraft(_Base):
    """GeneratePack output. Read-only — AI-generated report content split
    into bounded sections.

    Previously a single ``content: str`` field carrying an entire
    markdown report. That made the JSON-output surface fragile: a stray
    unescaped quote anywhere in the report broke the parse for the
    whole pack. Splitting into sections bounds the failure surface and
    makes each per-section content small enough that the model's
    JSON-mode decoder is unlikely to drift mid-string.
    """

    pack: str = Field(..., description="Which pack was requested.")
    sections: list[ReportSection] = Field(
        default_factory=list,
        description="Report sections in render order.",
    )

    def render_markdown(self) -> str:
        """Concatenate sections into one markdown document."""
        return "\n\n".join(
            f"## {section.heading}\n\n{section.content}".rstrip()
            for section in self.sections
        )


class PeerReviewResult(_Base):
    """SyntheticPeerReview output. Read-only — structured peer review."""

    reviewer_role: str = Field(..., description="Persona the reviewer adopted.")
    scope_assessment: str = Field(..., description="Is the model's scope appropriate?")
    rigor_assessment: str = Field(..., description="Are the causal claims well-founded?")
    evidence_assessment: str = Field(..., description="Is the evidence base adequate?")
    major_risks: list[str] = Field(default_factory=list, description="Key risks identified.")
    proposed_questions: list[str] = Field(
        default_factory=list,
        description="Questions the reviewer would ask the modeller.",
    )


class ResearchGap(_Base):
    """A single identified gap in the model's evidence or structure."""

    description: str = Field(..., description="What is missing or under-supported.")
    priority: str = Field(..., description="high | medium | low")
    affected_node_ids: list[str] = Field(
        default_factory=list,
        description="Nodes most affected by closing this gap.",
    )
    suggested_action: str = Field("", description="What the modeller should do.")


class ResearchGapsResult(_Base):
    """IdentifyResearchGaps output — hybrid prose + bounded mutation.

    Each ``ResearchGap`` carries a description, priority, and suggested
    action. ``apply()`` parks each gap as an ``OpenQuestion`` record so
    the gap is tracked through the normal question/discharge workflow
    rather than being lost in a transcript. Questions are attached to
    affected nodes when the AI provides them.
    """

    gaps: list[ResearchGap] = Field(default_factory=list)
    record_as_questions: bool = Field(
        True,
        description=(
            "Whether to log each gap as an OpenQuestion record. Default "
            "True. Set False when the gaps are exploratory and shouldn't "
            "yet enter the audit trail."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        created: list[str] = []
        if not self.record_as_questions:
            return created
        for gap in self.gaps:
            target_id = gap.affected_node_ids[0] if gap.affected_node_ids else None
            # Frame the gap as a question reviewers can discharge.
            qtext = (
                f"[{gap.priority}] {gap.description}"
                + (f" — Suggested: {gap.suggested_action}" if gap.suggested_action else "")
            )
            entry, _ = add_question(
                qtext,
                target_id=target_id,
                root=paths.root,
            )
            created.append(entry.id)
        return created


class FormalViewProjectionResult(_Base):
    """ProjectToFormalView output. Read-only — view projection recommendations."""

    target_view: str = Field(..., description="Which view was requested (cld | dag).")
    recommended_mappings: list[dict[str, str]] = Field(
        default_factory=list,
        description="Suggested entity/edge → view element mappings.",
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description="View constraint violations (e.g. cycles in DAG, missing polarity in CLD).",
    )
    rationale: str = Field("", description="Overall projection reasoning.")


# ---------- Reference management proposals/results ----------


class SearchQuery(_Base):
    """A targeted search query for finding relevant literature."""

    query: str = Field(..., description="Search keywords for Semantic Scholar.")
    rationale: str = Field("", description="Why this search would strengthen the model.")


class BibliographySearchPlan(_Base):
    """ExpandBibliography LLM output — search queries, not full references.

    The server takes these queries, searches Semantic Scholar, and builds
    the actual ExpandBibliographyProposal from real results.
    """

    queries: list[SearchQuery] = Field(default_factory=list)


class ExpandBibliographyProposal(_Base):
    """ExpandBibliography output.  Proposed new references to add to the library."""

    new_references: list[CitationSuggestion] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        known_bibkeys = {r.bibkey for r in list_references(paths.root)}
        created: list[str] = []
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
            created.append(added.bibkey)
            known_bibkeys.add(added.bibkey)
        return created


class UncitedElement(_Base):
    """An element that lacks evidence links."""

    element_id: str = Field(..., description="Node or edge ID.")
    label: str = Field("", description="Human-readable label.")
    attributes_without_evidence: list[str] = Field(
        default_factory=list,
        description="Attributes on this element with no citations.",
    )


class EvidenceLinkSuggestion(_Base):
    """A pattern-matched suggestion that an existing reference supports a
    specific (target, attribute) pair. Used by hybrid adversarial prompts
    that surface evidence-coverage gaps and propose closures."""

    target_id: str = Field(..., description="Entity or edge ID receiving the link.")
    attribute: str = Field(
        "existence",
        description=(
            "Attribute being supported. Default 'existence' means the "
            "reference supports the entity/edge as a whole. Other valid "
            "values include 'description', 'polarity', 'confidence', etc."
        ),
    )
    bibkey: str = Field(..., description="Bibkey of an existing reference in the library.")
    rationale: str = Field(
        "",
        description="One-line note on why this reference supports the target.",
    )


class CrossReferenceCheckResult(_Base):
    """CrossReferenceCheck output — hybrid prose + bounded mutation.

    The prose (``coverage_summary``, ``uncited_elements``,
    ``unused_references``) renders into the report. The structured
    ``suggested_links`` are evidence-link proposals that pair existing
    references in the library with currently-uncited elements; each is
    committed via ``add_evidence``.

    Bounded-mutation principle: only suggest links the AI has high
    confidence about. The audit prose is the deliverable; mutations are
    a bonus closure, not the main output.
    """

    uncited_elements: list[UncitedElement] = Field(default_factory=list)
    unused_references: list[str] = Field(
        default_factory=list,
        description="Bibkeys of references not cited by any element.",
    )
    coverage_summary: str = Field("", description="Overall evidence coverage assessment.")
    suggested_links: list[EvidenceLinkSuggestion] = Field(
        default_factory=list,
        description=(
            "Optional pattern-matched evidence-link suggestions: pairs "
            "of (existing reference bibkey, uncited element) where the "
            "AI judges the link plausible. Committed via add_evidence."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        created: list[str] = []
        for link in self.suggested_links:
            entry, _ = add_evidence(
                link.target_id,
                link.attribute,
                link.bibkey,
                verified_by="ai",
                notes=link.rationale or None,
                root=paths.root,
            )
            descriptor = f"evidence:{link.bibkey}->{link.target_id}/{link.attribute}"
            created.append(descriptor)
        return created


class ReferenceRelevanceResult(_Base):
    """SummarizeReference output. Read-only — relevance of one reference to the model."""

    bibkey: str = Field(..., description="The reference being summarized.")
    relevance_summary: str = Field(..., description="How this reference relates to the model.")
    connected_elements: list[str] = Field(
        default_factory=list,
        description="Element labels that this reference supports or could support.",
    )


class InterpretProseResult(_Base):
    """Interpret* prompt output. Read-only — AI-generated interpretation prose."""

    prose: str = Field(..., description="The generated interpretation text (Markdown).")
    key_references: list[str] = Field(
        default_factory=list,
        description="Finding or reference IDs cited in the interpretation.",
    )


# ── Compose extraction results ────────────────────────────────────────


class ExtractedVariable(_Base):
    """A single variable extracted from evidence."""

    label: str = Field(..., description="Concise variable/concept name.")
    kind: EntityKind = Field(
        "variable",
        description=(
            "Entity kind. Must be one of: concept, variable, event, actor, "
            "state, decision, hazard."
        ),
    )
    description: str = Field("", description="What this variable represents.")
    source_bibkeys: list[str] = Field(default_factory=list, description="References where found.")


class ExtractedVariablesResult(_Base):
    """ExtractVariablesFromEvidence output. Read-only — no apply()."""

    variables: list[ExtractedVariable] = Field(default_factory=list)


class ExtractedClaim(_Base):
    """A single causal claim extracted from evidence."""

    from_label: str = Field(..., description="Source entity label.")
    to_label: str = Field(..., description="Target entity label.")
    kind: str = Field("causal", description="Edge kind: causal, temporal, association.")
    description: str = Field(
        "",
        description="One sentence: the mechanism this edge represents.",
    )
    rationale: str = Field("", description="Brief explanation of the causal mechanism.")
    source_bibkeys: list[str] = Field(default_factory=list, description="References supporting this claim.")
    claim_text: str = Field("", description="Direct quote or paraphrase from the reference.")


class ExtractedClaimsResult(_Base):
    """ExtractCausalClaims output. Read-only — no apply()."""

    claims: list[ExtractedClaim] = Field(default_factory=list)


# ── AI synthesis results ──────────────────────────────────────────────


class SuggestedVariable(_Base):
    """A single AI-suggested variable."""

    label: str = Field(..., description="Concise variable/concept name.")
    kind: EntityKind = Field(
        "variable",
        description=(
            "Entity kind. Must be one of: concept, variable, event, actor, "
            "state, decision, hazard."
        ),
    )
    description: str = Field("", description="What this variable represents and why it matters.")
    rationale: str = Field("", description="Why this variable should be in the model.")


class SuggestedVariablesResult(_Base):
    """SuggestVariables output. Read-only — no apply()."""

    variables: list[SuggestedVariable] = Field(default_factory=list)


class SuggestedConnection(_Base):
    """A single AI-suggested connection."""

    from_label: str = Field(..., description="Source entity label.")
    to_label: str = Field(..., description="Target entity label.")
    kind: str = Field("causal", description="Edge kind.")
    description: str = Field(
        "",
        description="One sentence: what this connection means / the mechanism.",
    )
    rationale: str = Field("", description="Brief explanation of the mechanism.")
    confidence: str = Field("medium", description="low | medium | high")


class SuggestedConnectionsResult(_Base):
    """SuggestConnections output. Read-only — no apply()."""

    connections: list[SuggestedConnection] = Field(default_factory=list)


# ── Attribute suggestion results (Configure workflow) ─────────────────


class AttributeSuggestion(_Base):
    """A single AI-suggested model attribute value."""

    edge_id: str = Field(..., description="Edge target ID.")
    attribute: str = Field(..., description="Attribute name (polarity, weight).")
    value: str = Field(..., description="Suggested value.")
    rationale: str = Field("", description="Why this value is appropriate.")
    confidence: str = Field("medium", description="low | medium | high")


class AttributeSuggestionsResult(_Base):
    """SuggestEdgePolarities output. Mutating — applies all suggestions via
    the Configure batch path.

    The model_type is derived from each suggestion's `attribute` name via
    the model_type registry (CLD owns 'polarity', FCM owns 'weight'); we
    don't ask the AI to emit it. Suggestions are grouped by
    (model_type, attribute) and committed in a single batch per group.
    """

    suggestions: list[AttributeSuggestion] = Field(default_factory=list)

    def apply(self, paths: ProjectPaths) -> list[str]:
        if not self.suggestions:
            return []
        from latris.operations.configure import batch_set_view_attributes
        from latris.schema.model_types import MODEL_TYPE_REGISTRY

        # attribute → model_type (assumes 1:1 in practice — polarity↔cld,
        # weight↔fcm). Raises if ambiguous.
        attr_to_model_type: dict[str, str] = {}
        for spec in MODEL_TYPE_REGISTRY.values():
            for attr in spec.model_attributes:
                if attr in attr_to_model_type and attr_to_model_type[attr] != spec.id:
                    raise ValueError(
                        f"attribute {attr!r} is claimed by multiple model "
                        f"types — apply() can't disambiguate."
                    )
                attr_to_model_type[attr] = spec.id

        from latris.operations.view_attributes import get_view_attributes

        # Group by (model_type, attribute).
        buckets: dict[tuple[str, str], list[AttributeSuggestion]] = {}
        for s in self.suggestions:
            mt = attr_to_model_type.get(s.attribute)
            if mt is None:
                # Unknown attribute — skip rather than crash. The AI may
                # have invented one; fail-safe is to drop it.
                continue
            buckets.setdefault((mt, s.attribute), []).append(s)

        applied: list[str] = []
        for (mt, attr), sugg in buckets.items():
            # Non-destructive: only WRITE values for edges that don't already
            # have one; where the suggestion disagrees with an existing value,
            # preserve it and record the disagreement as a question.
            existing = {
                e.target_id: str(e.value) for e in get_view_attributes(mt, attr, root=paths.root).entries
            }
            to_write: list[dict] = []
            for s in sugg:
                current = existing.get(s.edge_id)
                if current is None:
                    to_write.append({
                        "target_id": s.edge_id,
                        "value": s.value,
                        "origin": "ai-proposed",
                        "source_detail": s.rationale[:200],
                    })
                elif current.strip() == str(s.value).strip():
                    continue  # already set to the same value — nothing to do
                else:
                    qid = _record_value_conflict(
                        s.edge_id, attr, str(s.value), current, s.rationale, paths
                    )
                    if qid:
                        applied.append(qid)
            if to_write:
                ids, _ = batch_set_view_attributes(
                    model_type=mt,
                    attribute=attr,
                    entries=to_write,
                    preserve_existing=True,
                    root=paths.root,
                )
                applied.extend(ids)
        return applied


class ApproachRecommendation(_Base):
    """One AI-recommended formalism for the project's modelling approach."""

    model_type_id: str = Field(..., description="Model-type id (e.g. cld, dag, bn).")
    suitability: str = Field("consider", description="recommended | consider | not_suited")
    rationale: str = Field(
        "", description="One sentence on why this formalism fits (or doesn't) this question/evidence."
    )


class ApproachRecommendationResult(_Base):
    """RecommendApproach output — ranked formalism recommendations.

    Read-only (no ``apply``): the user accepts recommendations, which select the
    model type and record the rationale as an auditable ModelChoice.
    """

    recommendations: list[ApproachRecommendation] = Field(default_factory=list)


# ── Inline per-field AI ───────────────────────────────────────────────


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


# ── Evidence-gap scan ─────────────────────────────────────────────────


class EvidenceGap(_Base):
    """A single evidence gap detected by ScanEvidenceGaps."""

    section_type: str = Field(
        ...,
        description=(
            "Interpret section the gap belongs to (key_findings, "
            "sensitivity, assumptions, evidence_gaps, evidence_coverage, "
            "answer, implications, confidence, open_questions, "
            "structural_summary)."
        ),
    )
    claim: str = Field(
        "",
        description="The specific claim, assumption, or finding the gap concerns.",
    )
    gap_description: str = Field(
        ..., description="What evidence is missing or weak."
    )
    suggested_action: str = Field(
        "",
        description=(
            "Concrete next step — e.g. 'search for studies on X', "
            "'add expert elicitation', 'validate against dataset Y'."
        ),
    )
    severity: str = Field(
        "medium", description="low | medium | high — for sorting/filtering in the GUI."
    )


class EvidenceGapsScanResult(_Base):
    """ScanEvidenceGaps output — hybrid prose + bounded mutation.

    The prose (``summary``, gap descriptions) renders into the report.
    ``apply()`` logs each gap as an ``OpenQuestion`` so it's tracked,
    and applies any AI-pattern-matched ``EvidenceLink`` suggestions
    to attach existing references to specific elements.

    Note: evidence-link suggestions only apply when the AI identifies a
    plausible reference *already in the library* that supports a
    specific (target, attribute). The AI cannot fabricate references
    here — those go through SuggestCitations.
    """

    gaps: list[EvidenceGap] = Field(default_factory=list)
    summary: str = Field(
        "",
        description="One-paragraph overview of the model's evidence health.",
    )
    record_as_questions: bool = Field(
        True,
        description="Whether to log each gap as an OpenQuestion record.",
    )
    suggested_evidence_links: list[EvidenceLinkSuggestion] = Field(
        default_factory=list,
        description=(
            "Optional: when the AI can match an existing reference "
            "(by bibkey) to an uncited element, suggest the link here. "
            "Each link is committed via add_evidence."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        created: list[str] = []
        if self.record_as_questions:
            for gap in self.gaps:
                qtext = (
                    f"[evidence/{gap.severity}] {gap.gap_description}"
                    + (f" — Suggested: {gap.suggested_action}" if gap.suggested_action else "")
                )
                entry, _ = add_question(
                    qtext,
                    root=paths.root,
                )
                created.append(entry.id)
        for link in self.suggested_evidence_links:
            entry, _ = add_evidence(
                link.target_id,
                link.attribute,
                link.bibkey,
                verified_by="ai",
                notes=link.rationale or None,
                root=paths.root,
            )
            # add_evidence returns (EvidenceLink, sha) but the link itself
            # has no id; use bibkey+target_id+attribute as the descriptor.
            descriptor = f"evidence:{link.bibkey}->{link.target_id}/{link.attribute}"
            created.append(descriptor)
        return created


# ---------- AI interrogation Phase 4a — VerifyClaimAgainstSource ----------


_VERIFY_VERDICTS = {"supports", "contradicts", "orthogonal", "insufficient_extract"}


class VerifyClaimAgainstSourceProposal(_Base):
    """`VerifyClaimAgainstSource` output.

    Hybrid: critique prose (`summary`) + a structured verdict. The
    apply()-time validator is the audit invariant — when the model
    claims `supports`, the server checks that the verbatim quote
    appears in the stored source_snapshot extract before accepting.
    The model cannot self-attest.
    """

    target_id: str | None = Field(
        None,
        description="Target element id (None for model-level links).",
    )
    attribute: str = Field(...)
    bibkey: str = Field(...)
    claim: str = Field(
        ...,
        description="Echo of the claim text being verified (for audit).",
    )
    verdict: str = Field(
        ...,
        description="One of supports / contradicts / orthogonal / insufficient_extract.",
    )
    quote: str | None = Field(
        None,
        description=(
            "Required when verdict=='supports'. Must appear verbatim in "
            "the Reference.source_snapshot.extract — checked at apply()."
        ),
    )
    summary: str = Field(
        "",
        description="Critique prose: what the source actually says vs. the claim.",
    )
    rationale: str = Field("", description="Short reasoning for the verdict.")
    confidence: str = Field("medium", description="One of: high, medium, low.")

    def apply(self, paths: ProjectPaths) -> list[str]:
        from latris.ai.context import _load_reference_for_verify
        from latris.schema import QuoteLocation

        if self.verdict not in _VERIFY_VERDICTS:
            raise ValueError(
                f"VerifyClaimAgainstSource invalid verdict {self.verdict!r}; "
                f"must be one of {sorted(_VERIFY_VERDICTS)}"
            )

        # Non-supports verdicts: no verbatim check needed. Just flip the
        # verdict via the operation.
        if self.verdict != "supports":
            link, _ = set_evidence_support_verdict(
                self.target_id,
                self.attribute,
                self.bibkey,
                new_verdict=self.verdict,  # type: ignore[arg-type]
                rationale=self.rationale or self.summary or "AI verification",
                root=paths.root,
            )
            return [f"{link.bibkey}:{link.target_id or 'model'}/{link.attribute}"]

        # supports — the audit-load-bearing path. Validate verbatim.
        if not self.quote:
            raise ValueError(
                "VerifyClaimAgainstSource verdict=supports requires a verbatim quote"
            )
        reference = _load_reference_for_verify(self.bibkey, paths)

        # Phase 4b: when a full-text artefact exists, validate against
        # the chunk identified by the proposal's quote_location.chunk_hash
        # (or any chunk that contains the quote — chunks overlap by 200
        # chars so the model has some leeway). Fall back to Phase 4a
        # behaviour against the source_snapshot.extract.
        location: QuoteLocation
        extract_path = paths.references_extract_path(self.bibkey)
        if extract_path.exists():
            from latris.operations._chunking import chunk_text

            full_text = extract_path.read_text(encoding="utf-8")
            chunks = chunk_text(full_text)
            matching = next((c for c in chunks if self.quote in c.text), None)
            if matching is None:
                raise ValueError(
                    "verbatim mismatch — model attested a quote that does not "
                    "appear in any chunk of the fetched source. Proposal rejected; "
                    "the audit invariant is that the apply-time check (not the "
                    "model) is the source of truth on whether a source "
                    "supports a claim."
                )
            offset_in_chunk = matching.text.index(self.quote)
            location = QuoteLocation(
                chunk_hash=matching.content_hash,
                page=None,
                offset=matching.offset + offset_in_chunk,
            )
        else:
            snapshot = reference.source_snapshot
            if snapshot is None or not snapshot.extract:
                raise ValueError(
                    f"reference {self.bibkey!r} has no source_snapshot.extract — "
                    "fetch a source snapshot before verifying"
                )
            if self.quote not in snapshot.extract:
                raise ValueError(
                    "verbatim mismatch — model attested a quote that does not "
                    "appear in the source snapshot. Proposal rejected; the "
                    "audit invariant is that the apply-time check (not the "
                    "model) is the source of truth on whether a source "
                    "supports a claim."
                )
            offset = snapshot.extract.index(self.quote)
            location = QuoteLocation(
                chunk_hash=snapshot.content_hash,
                page=None,
                offset=offset,
            )
        link, _ = set_evidence_support_verdict(
            self.target_id,
            self.attribute,
            self.bibkey,
            new_verdict="supports",
            rationale=self.rationale or self.summary or "verbatim match against source snapshot",
            quote=self.quote,
            quote_location=location,
            root=paths.root,
        )
        return [f"{link.bibkey}:{link.target_id or 'model'}/{link.attribute}"]


# ---------- AI interrogation Phase 3b — ChallengeEdge ----------


_CHALLENGE_EDGE_ACTIONS = {"evidence_search", "polarity_flip", "remove"}
_VALID_POLARITIES = {"+", "-", "~"}


class ChallengeEdgeProposal(_Base):
    """`ChallengeEdge` output. Hybrid: critique prose + one action.

    Element-scope (one edge per call). The critique lives in `summary`
    and is shown alongside the apply summary.
    """

    target_id: str = Field(..., description="Edge id this proposal acts on.")
    action: str = Field(
        ...,
        description="One of: evidence_search, polarity_flip, remove.",
    )
    summary: str = Field(
        "",
        description="Critique prose — the strongest counter-mechanism against the edge as encoded.",
    )
    rationale: str = Field("", description="Why this specific action repairs (or replaces) the edge.")
    confidence: str = Field(
        "medium",
        description="One of: high, medium, low.",
    )
    # Action-specific payloads (only one set, dictated by `action`):
    search_query: str | None = Field(
        None,
        description="Required when action=evidence_search. Literal search string for Semantic Scholar / OpenAlex / etc.",  # noqa: E501
    )
    new_polarity: str | None = Field(
        None,
        description="Required when action=polarity_flip. One of: +, -, ~ (ambiguous).",
    )
    model_type: str = Field(
        "cld",
        description="Active model type — needed for polarity_flip to write to the right view-attribute file.",
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        if self.action == "evidence_search":
            if not self.search_query:
                raise ValueError("ChallengeEdge evidence_search requires search_query")
            text = self.search_query
            if self.rationale:
                text = f"{text}\n\nWhy: {self.rationale}"
            entry, _ = add_question(text, target_id=self.target_id, root=paths.root)
            return [entry.id]
        if self.action == "polarity_flip":
            if self.new_polarity not in _VALID_POLARITIES:
                raise ValueError(
                    f"ChallengeEdge polarity_flip requires new_polarity in {sorted(_VALID_POLARITIES)}; "
                    f"got {self.new_polarity!r}"
                )
            target_id, _ = set_view_attribute(
                self.target_id,
                self.model_type,
                "polarity",
                self.new_polarity,
                root=paths.root,
            )
            return [target_id]
        if self.action == "remove":
            edge, _ = remove_edge(
                self.target_id,
                rationale=self.rationale or self.summary or None,
                root=paths.root,
            )
            return [edge.id]
        raise ValueError(
            f"ChallengeEdge invalid action {self.action!r}; must be one of {sorted(_CHALLENGE_EDGE_ACTIONS)}"
        )


# ---------- AI interrogation Phase 3b — EvidenceDemote ----------


_DEMOTE_ACTIONS = {"change_verdict", "remove"}
_DEMOTE_VERDICTS = {"unverified", "supports", "contradicts", "orthogonal", "insufficient_extract"}


class EvidenceDemoteProposal(_Base):
    """`EvidenceDemote` output. Hybrid: critique prose + one action.

    Element-scope (one (target, attribute, bibkey) link per call).
    """

    target_id: str | None = Field(
        None,
        description="Target element id (None when the link supports the model as a whole).",
    )
    attribute: str = Field(..., description="Attribute the link claims to support.")
    bibkey: str = Field(..., description="Reference bibkey identifying the citation.")
    action: str = Field(..., description="One of: change_verdict, remove.")
    summary: str = Field(
        "",
        description="Critique prose — what the source says vs. what the claim asserts.",
    )
    rationale: str = Field("", description="Why this action.")
    confidence: str = Field("medium", description="One of: high, medium, low.")
    new_verdict: str | None = Field(
        None,
        description=(
            "Required when action=change_verdict. One of unverified, "
            "supports, contradicts, orthogonal, insufficient_extract."
        ),
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        if self.action == "change_verdict":
            if self.new_verdict not in _DEMOTE_VERDICTS:
                raise ValueError(
                    f"EvidenceDemote change_verdict requires new_verdict in {sorted(_DEMOTE_VERDICTS)}; "
                    f"got {self.new_verdict!r}"
                )
            link, _ = set_evidence_support_verdict(
                self.target_id,
                self.attribute,
                self.bibkey,
                new_verdict=self.new_verdict,  # type: ignore[arg-type]
                rationale=self.rationale or self.summary or "AI demote",
                root=paths.root,
            )
            return [f"{link.bibkey}:{link.target_id or 'model'}/{link.attribute}"]
        if self.action == "remove":
            link, _ = remove_evidence(
                self.target_id,
                self.attribute,
                self.bibkey,
                rationale=self.rationale or self.summary or None,
                root=paths.root,
            )
            return [f"{link.bibkey}:{link.target_id or 'model'}/{link.attribute}"]
        raise ValueError(
            f"EvidenceDemote invalid action {self.action!r}; must be one of {sorted(_DEMOTE_ACTIONS)}"
        )


# ---------- AI interrogation Phase 3a — EdgeReclassify ----------


_RECLASSIFY_TARGET_KINDS = {"causal", "decision_rule", "governance", "definitional"}


class EdgeReclassifyAction(_Base):
    """One per-edge action emitted by `EdgeReclassify`.

    `action` ∈ {keep, retag, remove}. When action is `retag`, `new_kind`
    must be one of the four reclassify-targets (causal | decision_rule |
    governance | definitional). When `remove`, `new_kind` is ignored.
    """

    target_id: str = Field(..., description="Edge id being acted on.")
    action: str = Field(
        ...,
        description="One of: keep, retag, remove.",
    )
    new_kind: str | None = Field(
        None,
        description="Required when action=retag. One of causal/decision_rule/governance/definitional.",
    )
    rationale: str = Field(
        "",
        description="Why this edge needs the change (or why it should be removed).",
    )
    confidence: str = Field(
        "medium",
        description="One of: high, medium, low — model's confidence in the call.",
    )


class EdgeReclassifyProposal(_Base):
    """`EdgeReclassify` output. Hybrid: critique prose + per-edge actions.

    The critique prose lives in `summary` and renders alongside the
    apply summary so reviewers see the headline misclassifications and
    the audit-trail records that landed.
    """

    actions: list[EdgeReclassifyAction] = Field(default_factory=list)
    summary: str = Field("", description="One-paragraph critique of the worst misclassifications.")
    approved_indices: list[int] | None = Field(
        None,
        description="Set by the reviewer to apply only a subset of actions.",
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        if self.approved_indices is None:  # noqa: SIM108
            indices = list(range(len(self.actions)))
        else:
            indices = self.approved_indices
        affected: list[str] = []
        for i in indices:
            if i < 0 or i >= len(self.actions):
                continue
            a = self.actions[i]
            if a.action == "keep":
                continue
            if a.action == "retag":
                if a.new_kind not in _RECLASSIFY_TARGET_KINDS:
                    raise ValueError(
                        f"EdgeReclassify retag target_id={a.target_id!r} has invalid new_kind {a.new_kind!r}; "
                        f"must be one of {sorted(_RECLASSIFY_TARGET_KINDS)}"
                    )
                edge, _ = retype_edge(a.target_id, a.new_kind, root=paths.root)  # type: ignore[arg-type]
                affected.append(edge.id)
            elif a.action == "remove":
                edge, _ = remove_edge(
                    a.target_id,
                    rationale=a.rationale or None,
                    root=paths.root,
                )
                affected.append(edge.id)
            else:
                raise ValueError(
                    f"EdgeReclassify target_id={a.target_id!r} has invalid action {a.action!r}; "
                    "must be one of keep/retag/remove"
                )
        return affected


# ── AI interrogation Phase 2c — CompletenessGate ───────────────────────


class MissingVariableProposal(_Base):
    """A single missing-variable record proposed by CompletenessGate."""

    name: str = Field(..., description="Short, human-readable variable label.")
    rationale: str = Field(..., description="Why the variable is necessary.")
    required_for: list[str] = Field(
        default_factory=list,
        description="Claims or open-question topics that depend on this variable.",
    )
    severity: str = Field(
        ...,
        description="One of: required, recommended, optional.",
    )
    confidence: str = Field(
        "medium",
        description="One of: high, medium, low. Gate's own confidence in the call.",
    )


class CompletenessGateResult(_Base):
    """CompletenessGate output. apply() merges entries into the per-model
    report YAML, preserving prior excluded / added_to_model rows.
    """

    coverage_ratio: float = Field(
        0.0,
        description="cited / total ratio across substrate elements at run time.",
    )
    entries: list[MissingVariableProposal] = Field(default_factory=list)
    model_type: str = Field(
        "cld",
        description="Model type the gate ran for. Echoed from inputs.",
    )

    def apply(self, paths: ProjectPaths) -> list[str]:
        from latris.operations.completeness import merge_gate_result

        report, _sha = merge_gate_result(self, root=paths.root)
        return [mv.id for mv in report.entries if mv.disposition == "open"]
