"""AI interrogation proposals: source verification, adversarial edge checks, the completeness gate."""

from __future__ import annotations

from pydantic import Field

from latris.ai.proposals._shared import _Base
from latris.operations.edges import remove_edge, retype_edge
from latris.operations.evidence import remove_evidence, set_evidence_support_verdict
from latris.operations.provenance import add_question
from latris.operations.view_attributes import set_view_attribute
from latris.repo.layout import ProjectPaths

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

        # supports — the audit-load-bearing path. The operation looks the
        # quote up in the fetched full text, the snapshot or the abstract,
        # and refuses an AI's quote it can't find (a paraphrase).
        if not self.quote:
            raise ValueError(
                "VerifyClaimAgainstSource verdict=supports requires a verbatim quote"
            )
        try:
            link, _ = set_evidence_support_verdict(
                self.target_id,
                self.attribute,
                self.bibkey,
                new_verdict="supports",
                rationale=self.rationale or self.summary or "verbatim match against source snapshot",
                quote=self.quote,
                checked_by="ai",
                root=paths.root,
            )
        except ValueError as exc:
            if "holds no text" in str(exc):
                raise ValueError(
                    f"reference {self.bibkey!r} has no source_snapshot.extract — "
                    "fetch a source snapshot before verifying"
                ) from exc
            if "isn't in the text" in str(exc):
                raise ValueError(
                    "verbatim mismatch — model attested a quote that does not appear in the "
                    "source's stored text (any chunk of the fetched source, the snapshot or the abstract). "
                    "Proposal rejected; the apply-time check (not the "
                    "model) is the source of truth on whether a source supports a claim."
                ) from exc
            raise
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


# ---------- AI interrogation Phase 2c — CompletenessGate ----------


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
