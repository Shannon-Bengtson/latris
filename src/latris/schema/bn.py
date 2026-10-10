"""Discrete Bayesian Network schema — state spaces + conditional probability tables.

A discrete BN over the substrate's causal-edge projection: every node is a
*chance* node with a finite, ordered state space and a conditional probability
table (CPT) giving ``P(node | parents)`` for every combination of parent states.

Stored (one file each, via the generic view-attribute path convention):

- ``views/parameters/bn-state_space.yaml`` — :class:`StateSpaceSet`
- ``views/parameters/bn-cpt.yaml``          — :class:`CPTSet`

Each CPT row carries its own provenance (origin / verification / source), so a
single elicited conditional distribution is independently attributable — and a
one-number edit is a one-line, sourced git diff.

Intrinsic structural integrity (row width, value range, parent-key validity) is
enforced here as pydantic validators. Cross-node *completeness* (every parent
combination present) and *normalisation* (each row sums to 1) are deliberately
left soft and checked by the readiness layer with tolerance — see
``operations/readiness.py``.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from latris.schema.attributes import _Base, _EntryBase
from latris.schema.common import (
    Informants,
    ProvenanceOrigin,
    ProvenanceVerification,
)


class StateSpaceEntry(_EntryBase):
    """The finite, ordered set of states a chance node can take.

    ``target_id`` (inherited) is the node id; ``ordered`` marks an ordinal
    state space (e.g. low < med < high) versus a nominal one.
    """

    attribute: str = "state_space"
    states: list[str]
    ordered: bool = False

    @model_validator(mode="after")
    def _check_states(self) -> StateSpaceEntry:
        if len(self.states) < 1:
            raise ValueError("a state space needs at least one state")
        if any(not s for s in self.states):
            raise ValueError("state names must be non-empty")
        if len(self.states) != len(set(self.states)):
            raise ValueError(f"duplicate state names in {self.states!r}")
        return self


class StateSpaceSet(_Base):
    entries: list[StateSpaceEntry] = Field(default_factory=list)


class CPTRow(_Base):
    """One conditional distribution: ``P(node | parents = parent_states)``.

    ``parent_states`` maps each parent node id to one of its states (empty for
    a root node). ``p`` is the distribution over the node's own states, in the
    node's state order. Provenance is per-row: each elicited conditional is
    independently sourced, so the value and its source sit adjacent in the diff.
    """

    parent_states: dict[str, str] = Field(default_factory=dict)
    p: list[float]
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None
    contested: bool = False
    informants: Informants = Field(default_factory=Informants)

    @model_validator(mode="after")
    def _check_probs(self) -> CPTRow:
        if not self.p:
            raise ValueError("a CPT row needs at least one probability")
        if any(not (0.0 <= v <= 1.0) for v in self.p):
            raise ValueError(f"probabilities must be in [0, 1], got {self.p!r}")
        return self


class CPTEntry(_EntryBase):
    """A node's full conditional probability table.

    ``parents`` is the ordered list of parent node ids (defines column order).
    ``states`` repeats the node's own state order for self-containment. ``rows``
    holds one :class:`CPTRow` per combination of parent states (row-major over
    the parents' state spaces). Per-row provenance is on each row; the inherited
    ``_EntryBase`` fields carry table-level provenance.
    """

    attribute: str = "cpt"
    parents: list[str] = Field(default_factory=list)
    states: list[str]
    rows: list[CPTRow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_shape(self) -> CPTEntry:
        if len(self.states) < 1:
            raise ValueError("a CPT needs a non-empty state space")
        if len(self.states) != len(set(self.states)):
            raise ValueError(f"duplicate state names in {self.states!r}")
        n = len(self.states)
        parent_set = set(self.parents)
        for row in self.rows:
            if len(row.p) != n:
                raise ValueError(
                    f"CPT row has {len(row.p)} probabilities but node {self.target_id!r} "
                    f"has {n} states {self.states!r}"
                )
            extra = set(row.parent_states) - parent_set
            if extra:
                raise ValueError(
                    f"CPT row conditions on non-parent node(s) {sorted(extra)}; "
                    f"parents are {self.parents!r}"
                )
        return self


class CPTSet(_Base):
    entries: list[CPTEntry] = Field(default_factory=list)


# ── Canonical models (Noisy-OR) ──────────────────────────────────────────
#
# A canonical model is a *compact parameterisation* that expands into a full
# CPT. We store the spec (not the 2^k expanded cells) as the source of truth,
# so the elicited object stays small and truthful: a node with k binary causes
# needs k cause-probabilities + 1 leak, not 2^k rows. Provenance lives on the
# spec; the expansion is derived at compute time. See ``operations/_bn_canonical``.


class NoisyOrLink(_Base):
    """One cause in a Noisy-OR: ``P(child active | only this cause active)``.

    ``active_state`` is the parent state that counts as the cause being
    "present"; the other state contributes nothing. Provenance is per-link —
    each cause's strength is independently sourced.
    """

    parent_id: str
    active_state: str
    prob: float
    origin: ProvenanceOrigin = "human-elicited"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None

    @model_validator(mode="after")
    def _check_prob(self) -> NoisyOrLink:
        if not (0.0 <= self.prob <= 1.0):
            raise ValueError(f"Noisy-OR link probability must be in [0, 1], got {self.prob!r}")
        return self


class NoisyOrEntry(_EntryBase):
    """A node's Noisy-OR parameterisation (binary node, binary causes).

    ``states`` is the node's binary state space with ``states[0]`` the "active"
    (occurs/positive) outcome the causes push toward. ``leak`` is
    ``P(active | all causes inactive)``. Expanding the spec gives, for each
    parent-state combination with active set S:
    ``P(active) = 1 - (1 - leak) · ∏_{i∈S} (1 - prob_i)``.
    """

    attribute: str = "noisy_or"
    parents: list[str] = Field(default_factory=list)
    states: list[str]
    leak: float = 0.0
    links: list[NoisyOrLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_spec(self) -> NoisyOrEntry:
        if len(self.states) != 2:
            raise ValueError(f"Noisy-OR is binary: node {self.target_id!r} needs exactly 2 states")
        if len(self.states) != len(set(self.states)):
            raise ValueError(f"duplicate state names in {self.states!r}")
        if not (0.0 <= self.leak <= 1.0):
            raise ValueError(f"leak must be in [0, 1], got {self.leak!r}")
        link_parents = [link.parent_id for link in self.links]
        if set(link_parents) != set(self.parents) or len(link_parents) != len(self.parents):
            raise ValueError(
                f"Noisy-OR for {self.target_id!r} needs exactly one link per parent; "
                f"parents={self.parents!r}, links cover {link_parents!r}"
            )
        return self


class NoisyOrSet(_Base):
    entries: list[NoisyOrEntry] = Field(default_factory=list)


# ── Sensitivity analysis ─────────────────────────────────────────────────


class SensitivityFinding(_Base):
    """How much one CPT conditional moves a target posterior, with provenance.

    A finding is per CPT row (one conditional distribution). ``influence`` is the
    range of the target posterior as the most-influential cell of that row is
    swept; ``state`` names that cell. The provenance fields are copied from the
    row so the tornado shows *where the influential numbers came from*.
    """

    node_id: str
    parent_states: dict[str, str] = Field(default_factory=dict)
    state: str
    influence: float
    baseline_prob: float
    origin: ProvenanceOrigin = "human-direct"
    verification: ProvenanceVerification = "unverified"
    source_id: str | None = None
    contested: bool = False
    weak: bool = False  # influential but not human-verified (or contested)


class SensitivityResult(_Base):
    target_id: str
    target_state: str
    evidence: dict[str, str] = Field(default_factory=dict)
    baseline: float
    inference_runs: int
    findings: list[SensitivityFinding] = Field(default_factory=list)
