"""What the proposal schemas share: the base model, the small entry types several of them carry
(an assumption, a question, a decision, an exclusion, a citation), and the helpers their ``apply()`` use."""

from __future__ import annotations

from contextlib import nullcontext
from typing import get_args

from pydantic import BaseModel, ConfigDict, Field

from latris.operations.attributes import set_attribute
from latris.operations.batch import batch, get_active_batch
from latris.operations.evidence import add_evidence
from latris.operations.provenance import add_assumption, add_question
from latris.operations.view_attributes import set_view_attribute
from latris.repo.layout import ProjectPaths
from latris.schema.attributes import Confidence


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


_VALID_CONFIDENCE = set(get_args(Confidence))


def _grouped_commit(paths: ProjectPaths, subject: str):
    """Collapse an apply()'s many writes into one commit — unless a batch is
    already active (nesting is unsupported), in which case defer to it."""
    if get_active_batch() is not None:
        return nullcontext()
    return batch(paths.root, subject=subject)


def _cld_selected(paths: ProjectPaths) -> bool:
    """True when the model type whose links carry polarity (the loop map) is selected — the gate for
    persisting co-authored edge polarity (that type's view attribute)."""
    from latris.operations import formalisms
    from latris.operations.project import load_foundation

    try:
        _, foundation = load_foundation(paths.root)
    except Exception:
        return False
    return formalisms.attribute_home("polarity") in set(foundation.selected_model_types or [])


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
