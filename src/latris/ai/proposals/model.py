"""Proposals and results about the model as a whole: drafted framings, new connections, attacks, reviews, gaps."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import (
    _ASSUMPTIONS_DESC,
    _CONFIDENCE_DESC,
    _SOURCE_BIBKEYS_DESC,
    DraftAssumption,
    ExclusionEntry,
    ProvenanceBundle,
    QuestionEntry,
    _apply_provenance_bundle,
    _Base,
    _bind_entity_provenance,
    _cld_selected,
    _grouped_commit,
    _persist_edge_polarity,
)
from latris.operations.attributes import set_attribute
from latris.operations.edges import DuplicateEdgeError, add_edge
from latris.operations.nodes import add_node, list_nodes
from latris.operations.provenance import add_assumption, add_exclusion, add_question
from latris.operations.references import list_references
from latris.repo.layout import ProjectPaths
from latris.schema.substrate import EntityKind, coerce_edge_kind, coerce_entity_kind


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
                try:
                    edge, _ = add_edge(from_id, to_id, kind=edge_kind, root=paths.root)
                except DuplicateEdgeError:
                    continue  # already in the model; never overwrite it with a parallel link
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
                try:
                    edge, _ = add_edge(p.from_id, p.to_id, kind=p.kind, root=paths.root)
                except DuplicateEdgeError:
                    continue  # already in the model; never overwrite it with a parallel link
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
            question, _ = add_question(
                self.follow_up_question,
                target_id=target_id,
                root=paths.root,
            )
            created.append(question.id)
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
            question, _ = add_question(
                q.question,
                root=paths.root,
            )
            created.append(question.id)
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
