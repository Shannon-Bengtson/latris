from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.common import (
    Informants,
    ProvenanceOrigin,
    ProvenanceVerification,
    QuoteLocation,
    SourceAccess,
    SupportVerdict,
)

Confidence = Literal["low", "medium", "high", "quantitative-pending"]
# Polarity values: "+" (positive), "-" (negative), "~" (ambiguous —
# evidence is genuinely contested or the relationship is non-monotonic;
# loop classification treats any "~" edge as making the loop unknown).
Polarity = Literal["+", "-", "~"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _EntryBase(_Base):
    """Common shape for every per-attribute entry.

    `target_id` is the Entity or Edge ID the attribute attaches to. `attribute`
    names the attribute within the file (redundant with filename but lets a file
    hold more than one attribute type if we ever want to; keeps diffs explicit).

    Maturity is no longer per-attribute — it lives on the parent Entity/Edge.
    Per-cell uncertainty is still expressible via Confidence and the
    EvidenceLink audit axes. Full design in
    docs/design/MATURITY_LADDER.md.
    """

    target_id: str
    attribute: str
    informants: Informants = Field(default_factory=Informants)
    contested: bool = False
    contested_views: list[str] = Field(default_factory=list)
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None


class DescriptionEntry(_EntryBase):
    attribute: str = "description"
    value: str


class DescriptionSet(_Base):
    entries: list[DescriptionEntry] = Field(default_factory=list)


class ConfidenceEntry(_EntryBase):
    attribute: str = "confidence"
    value: Confidence


class ConfidenceSet(_Base):
    entries: list[ConfidenceEntry] = Field(default_factory=list)


class PolarityEntry(_EntryBase):
    attribute: str = "polarity"
    value: Polarity
    # Free-text causal story for the polarity. The coherence check lints this
    # against the edge description; authoring it in the same call that sets the
    # polarity (see ai/proposals._persist_edge_polarity) keeps the two coherent.
    rationale: str | None = None


class PolaritySet(_Base):
    entries: list[PolarityEntry] = Field(default_factory=list)


class FloatEntry(_EntryBase):
    """Numeric attribute entry — continuous value with full provenance.

    Generic entry for any float-valued parameter: FCM edge weights,
    fault-tree probabilities, Markov transition rates, etc.  The
    ``attribute`` field distinguishes the parameter kind; range
    constraints live in the coercion function, not the schema.
    """

    attribute: str
    value: float


class FloatSet(_Base):
    entries: list[FloatEntry] = Field(default_factory=list)


class ParameterUncertainty(_EntryBase):
    """Uncertainty distribution annotation for a parameter cell.

    Associates a probability distribution with a quantitative parameter
    value, enabling PSA (Probabilistic Sensitivity Analysis) and EVPI
    computation.  Each distribution choice is a modelling decision with
    its own provenance — who chose Beta(2,5) and why?

    Schema shell for now — operations will be added in the quantitative
    modelling phases.
    """

    attribute: str = "uncertainty"
    distribution: str = "unknown"  # e.g. "beta", "gamma", "lognormal", "uniform", "triangular", "normal"
    params: dict[str, float] = Field(default_factory=dict)  # e.g. {"alpha": 2.0, "beta": 5.0}
    parameter_cell_id: str | None = None  # links to the parameter entry this annotates


class ParameterUncertaintySet(_Base):
    entries: list[ParameterUncertainty] = Field(default_factory=list)


class EvidenceLink(_Base):
    """A citation attached to a specific (target, attribute) pair.

    Per the concept doc: citations attach to attributes, not bare entities.
    When target_id is None, the evidence supports the project/model as a whole.

    Provenance is split across four orthogonal axes (Phase 1 of the AI
    interrogation layer, see docs/design/AI_INTERROGATION.md):

    - ``verified_by``: who proposed it (human or ai)
    - ``source_access``: what the proposer actually saw at proposal time
    - ``support_verdict``: whether the source backs the specific claim
    - ``quote`` + ``quote_location``: verbatim supporting span

    A single ``ai-verified`` label conflated all four; the new shape
    makes structural lies (AI labelled a paper "verified" without
    reading it) impossible to express.
    """

    target_id: str | None = None
    attribute: str
    bibkey: str
    informants: Informants = Field(default_factory=Informants)
    notes: str | None = None
    origin: ProvenanceOrigin = "human-direct"
    source_id: str | None = None

    # Audit axes
    verified_by: Literal["human", "ai"] = "human"
    source_access: SourceAccess = "title_only"
    support_verdict: SupportVerdict = "unverified"
    quote: str | None = None
    quote_location: QuoteLocation | None = None


class EvidenceLinkSet(_Base):
    entries: list[EvidenceLink] = Field(default_factory=list)


class DataLink(_Base):
    """Data-driven evidence attached to a specific (target, attribute) pair.

    Parallel to EvidenceLink but for data-derived evidence. When a node or edge
    is created from a dataset column or a statistical relationship, a DataLink
    records the provenance: which dataset, which column(s), what was measured.
    """

    target_id: str | None = None
    attribute: str = "existence"
    dataset_id: str
    column_names: list[str] = Field(default_factory=list)
    statistic: str | None = None  # e.g. "correlation", "distribution", "column-mapping"
    value: str | None = None  # e.g. "r=0.72, p<0.01", "mean=23.4"
    rationale: str | None = None
    notes: str | None = None
    informants: Informants = Field(default_factory=Informants)
    origin: ProvenanceOrigin = "data-derived"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None


class DataLinkSet(_Base):
    entries: list[DataLink] = Field(default_factory=list)
