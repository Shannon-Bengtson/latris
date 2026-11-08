from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from latris.schema.common import (
    Informants,
    ProvenanceOrigin,
    ProvenanceVerification,
    QuoteLocation,
    SourceAccess,
    SupportVerdict,
)

# "by-definition": true by definition or accounting (departures reduce the
# number of volunteers) — certain, and needs no source.
Confidence = Literal["low", "medium", "high", "quantitative-pending", "by-definition"]
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


Distribution = Literal["unknown", "uniform", "triangular", "normal", "lognormal", "beta", "gamma"]

# Parameters each distribution needs, and the optional ones it accepts. Values
# are in the annotated parameter's own units (e.g. a constant in tonne/year).
DISTRIBUTION_PARAMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "unknown": ((), ()),
    "uniform": (("min", "max"), ()),
    "triangular": (("min", "mode", "max"), ()),
    "normal": (("mean", "sd"), ("min", "max")),  # min/max truncate
    "lognormal": (("mean", "sd"), ("min", "max")),  # mean/sd of the value itself, not of its log
    "beta": (("alpha", "beta"), ("min", "max")),  # scaled to [min, max], default [0, 1]
    "gamma": (("shape", "scale"), ("min", "max")),
}


class ParameterUncertainty(_EntryBase):
    """How uncertain a quantitative parameter is: a distribution over its value.

    Monte Carlo runs sample from it, and one-at-a-time sensitivity uses its
    5th–95th percentile range. Each distribution choice is a modelling
    decision with its own provenance — who chose Triangular(80, 120, 150) and
    why — recorded in ``origin``/``source_id``/``reason``.

    ``parameter_cell_id`` names what is annotated: ``sd:constant`` or
    ``sd:initial_value`` for System Dynamics.
    """

    attribute: str = "uncertainty"
    distribution: Distribution = "unknown"
    params: dict[str, float] = Field(default_factory=dict)  # e.g. {"min": 80, "mode": 120, "max": 150}
    parameter_cell_id: str | None = None  # links to the parameter entry this annotates
    reason: str = ""

    @model_validator(mode="after")
    def _check_params(self) -> ParameterUncertainty:
        required, optional = DISTRIBUTION_PARAMS[self.distribution]
        missing = [k for k in required if k not in self.params]
        unknown = [k for k in self.params if k not in required + optional]
        if missing or unknown:
            need = ", ".join(required) or "nothing"
            raise ValueError(
                f"a {self.distribution} distribution needs {need}"
                + (f" (optional: {', '.join(optional)})" if optional else "")
                + (f"; missing {', '.join(missing)}" if missing else "")
                + (f"; unexpected {', '.join(unknown)}" if unknown else "")
            )
        p = self.params
        if "min" in p and "max" in p and not p["min"] < p["max"]:
            raise ValueError("min must be less than max")
        if self.distribution == "triangular" and not p["min"] <= p["mode"] <= p["max"]:
            raise ValueError("a triangular distribution needs min ≤ mode ≤ max")
        for key in ("sd", "alpha", "beta", "shape", "scale"):
            if key in p and p[key] <= 0:
                raise ValueError(f"{key} must be positive")
        if self.distribution == "lognormal" and p["mean"] <= 0:
            raise ValueError("a lognormal distribution needs a positive mean")
        return self


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

    ``stance`` says what the citation is offered as (evidence for the claim
    or against it); ``support_verdict`` stays the result of someone reading
    the source, so citing a source as "against" never counts as checking
    it. ``quote_verified`` says whether a check's quote was found in the
    stored text of the source (None: no quote).

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
    stance: Literal["for", "against"] = "for"
    quote: str | None = None
    quote_location: QuoteLocation | None = None
    quote_verified: bool | None = None

    @property
    def is_against(self) -> bool:
        """Evidence against the claim: cited as against it, or checked and found to contradict it."""
        return self.stance == "against" or self.support_verdict == "contradicts"

    @property
    def checked(self) -> bool:
        return self.support_verdict != "unverified"


class EvidenceLinkSet(_Base):
    entries: list[EvidenceLink] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _split_stance(cls, data):  # noqa: ANN001, ANN206
        # Before 0.7.7 a source cited as against a claim was stored as
        # support_verdict=contradicts, as if it had been checked. On load,
        # unless a check recorded that verdict (its note says
        # "→ contradicts"), it becomes an unchecked citation against it.
        if not isinstance(data, dict):
            return data
        entries = []
        for e in data.get("entries") or []:
            if isinstance(e, dict) and "stance" not in e and e.get("support_verdict") == "contradicts":
                e = {**e, "stance": "against"}
                if not re.search(r"→ contradicts", e.get("notes") or ""):
                    e["support_verdict"] = "unverified"
            entries.append(e)
        return {**data, "entries": entries}


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
