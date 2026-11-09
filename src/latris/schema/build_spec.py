"""A whole model in one file, for ``latris build --spec``.

Agents otherwise build a model one command (and one commit) at a time —
about a hundred calls for a dozen factors. A spec carries the same content
in one YAML or JSON document; the field names match the remote MCP
server's ``apply_changes`` operations so one vocabulary serves both.

    outcome: Volunteer departures
    factors:
      - label: Volunteer burnout
        description: Emotional and physical exhaustion from volunteering.
    links:
      - from: Workload per volunteer
        to: Volunteer burnout
        polarity: "+"
        reason: More hours per person, more exhaustion.
        confidence: high
        sources: [smith2024]
        contradicts: [tuohy2015]   # sources that argue against this link
    sources:
      - key: smith2024
        title: Burnout among community volunteers
        authors: ["Smith, Jane"]
        year: 2024
      - key: tuohy2015
        title: Workload and volunteer retention revisited
        year: 2015
    assumptions:
      - Volunteers' hours are roughly comparable across programs.
    questions:
      - Does recognition reduce departures independently of workload?
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from latris.schema.attributes import Confidence
from latris.schema.common import ProvenanceOrigin
from latris.schema.references import SourceSnapshotKind
from latris.schema.substrate import EdgeKind, EntityKind


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SpecCitation(_Spec):
    """A source cited on a factor or link, by its reference key."""

    key: str
    notes: str | None = None


class SpecFactor(_Spec):
    label: str
    kind: EntityKind = "variable"
    description: str | None = None
    sources: list[str | SpecCitation] = Field(default_factory=list)
    contradicts: list[str | SpecCitation] = Field(default_factory=list)


class SpecLink(_Spec):
    from_: str = Field(alias="from")
    to: str
    kind: EdgeKind = "causal"
    polarity: Literal["+", "-"] | None = None
    reason: str | None = None  # why the polarity holds (the causal story)
    weight: float | None = Field(default=None, ge=-1, le=1)  # FCM edge weight
    description: str | None = None
    confidence: Confidence | None = None  # low | medium | high | quantitative-pending | by-definition
    sources: list[str | SpecCitation] = Field(default_factory=list)
    contradicts: list[str | SpecCitation] = Field(default_factory=list)  # sources against the link


class SpecSource(_Spec):
    key: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container: str | None = None
    doi: str | None = None
    url: str | None = None
    notes: str | None = None  # e.g. sample size, key result
    # What was actually read: an abstract or passage (≤ ~2000 chars), so a
    # check of the source is grounded in visible text.
    extract: str | None = Field(None, max_length=4000)
    extract_url: str | None = None  # where the extract came from; defaults to url
    extract_kind: SourceSnapshotKind = "abstract"
    cited_via: str | None = None  # key of the source this one was read in (e.g. a review)


# A link is named by its two ends, "From -> To" (or "From → To").
LINK_ARROWS = ("->", "→")


class SpecAssumption(_Spec):
    text: str
    target: str | None = None  # a factor label, or a link as "From -> To"
    rationale: str | None = None


class SpecFinding(_Spec):
    """Recorded as proposed: approving a finding is a person's act, done in the tool."""

    statement: str
    category: Literal["structure", "dynamics", "sensitivity", "inference", "diagnostics", "recommendations"] = (
        "structure"
    )
    detail: str = ""
    targets: list[str] = Field(default_factory=list)  # factor labels or "From -> To"


class SpecDecision(_Spec):
    """A modelling choice and why it was made (e.g. leaving a factor out)."""

    statement: str
    rationale: str
    target: str | None = None  # a factor label, or a link as "From -> To"


class SpecChallenge(_Spec):
    """An open challenge: someone disputes a factor or link."""

    argument: str
    target: str | None = None  # a factor label, or a link as "From -> To"


class SpecInterpretation(_Spec):
    """Prose for one interpretation section (e.g. answer_to_question)."""

    section: str
    prose: str
    by: Literal["ai", "human"] = "ai"


class SpecContext(_Spec):
    """The situation the model is built in. Shown at the top of the report."""

    background: str | None = None  # the situation behind the question
    audience: str | None = None  # who will read it ("Prepared for")
    boundary: str | None = None  # what's in and out of scope
    intuition: str | None = None  # what the person expects the answer to be, in their words


# ── quantitative parameters (System Dynamics, Bayesian networks) ─────────
# Field names match the MCP server's apply_changes operations (set_sd_role,
# set_equation, set_constant, set_initial_value, set_table, set_states,
# set_probability_table, set_noisy_or). Nodes are named by label.


class _SpecParam(_Spec):
    origin: ProvenanceOrigin | None = None  # default: ai-proposed when built --verified-by ai, else human-direct
    source: str | None = None  # a source key (or analysis run id) the value comes from


class SpecSDRole(_Spec):
    node: str
    role: Literal["stock", "flow", "auxiliary", "constant", "source_sink"]


class SpecSDEquation(_SpecParam):
    node: str
    expression: str
    units: str


class SpecSDValue(_SpecParam):
    node: str
    value: float
    units: str


class SpecSDStock(SpecSDValue):
    non_negative: bool = False


class SpecSDTable(_SpecParam):
    node: str
    points: list[tuple[float, float]] = Field(min_length=2)
    x_units: str
    y_units: str
    extrapolate: Literal["clamp", "linear"] = "clamp"


class SpecUncertainty(_SpecParam):
    """A distribution over a constant's or stock's value, in its own units."""

    node: str
    distribution: Literal["uniform", "triangular", "normal", "lognormal", "beta", "gamma"]
    params: dict[str, float]
    reason: str = ""


class SpecScenario(_Spec):
    """A named what-if: ``set`` holds 'Variable=value [units]' assignments."""

    name: str
    set: list[str] = Field(min_length=1)
    description: str = ""
    reason: str = ""
    origin: ProvenanceOrigin | None = None
    source: str | None = None


class SpecSD(_Spec):
    # The clock and run settings: time_units, initial_time, final_time, dt, saveper, integration_method.
    settings: dict[str, float | str] = Field(default_factory=dict)
    roles: list[SpecSDRole] = Field(default_factory=list)
    stocks: list[SpecSDStock] = Field(default_factory=list)  # initial values
    constants: list[SpecSDValue] = Field(default_factory=list)
    equations: list[SpecSDEquation] = Field(default_factory=list)
    tables: list[SpecSDTable] = Field(default_factory=list)
    uncertainty: list[SpecUncertainty] = Field(default_factory=list)
    scenarios: list[SpecScenario] = Field(default_factory=list)


class SpecBNStates(_Spec):
    node: str
    states: list[str] = Field(min_length=2)
    ordered: bool = False


class SpecBNTable(_SpecParam):
    """probabilities: one block per parent-state combination (first parent slowest), in state order."""

    node: str
    parents: list[str] = Field(default_factory=list)
    probabilities: list[float] = Field(min_length=1)


class SpecNoisyOrCause(_Spec):
    parent: str
    active_state: str
    probability: float = Field(ge=0, le=1)


class SpecNoisyOr(_SpecParam):
    node: str
    causes: list[SpecNoisyOrCause] = Field(min_length=1)
    leak: float = Field(0.0, ge=0, le=1)
    active: str | None = None  # the node's state the causes push toward (the effect happening)


class SpecBNUncertainty(_SpecParam):
    """How well a probability table is known: worth about ``n`` observations (``row``: one row only)."""

    node: str
    n: float = Field(gt=0)
    row: str | None = None  # "Parent=state,Other=state"
    reason: str = ""


class SpecBN(_Spec):
    states: list[SpecBNStates] = Field(default_factory=list)
    tables: list[SpecBNTable] = Field(default_factory=list)
    noisy_or: list[SpecNoisyOr] = Field(default_factory=list)
    uncertainty: list[SpecBNUncertainty] = Field(default_factory=list)


class SpecAnalysis(_Spec):
    """An analysis to run (and record, so the report shows it) once the model is built.

    kind: simulate (scenarios, set) | monte_carlo (runs, seed, sampling, variables, scenario)
    | sensitivity (variable, metric, pct, scenario) | loops (scenario, start, end)
    | bn_query (evidence, soft, likelihood, query) | bn_explain (evidence, soft, likelihood, over)
    | bn_monte_carlo (target, state, evidence, soft, likelihood, runs, seed)
    | bn_sensitivity (target, state, evidence).
    ``soft`` is {node: {state: probability}} (certainty); ``likelihood`` {node: {state: weight}}.
    ``settings``: initial_time, final_time, dt, saveper, method, time_units.
    """

    kind: Literal[
        "simulate", "monte_carlo", "sensitivity", "loops", "bn_query", "bn_explain", "bn_monte_carlo",
        "bn_sensitivity",
    ]
    settings: dict[str, float | str] = Field(default_factory=dict)
    scenarios: list[str] = Field(default_factory=list)
    set: list[str] = Field(default_factory=list)
    scenario: str | None = None
    runs: int | None = None
    seed: int | None = None
    sampling: Literal["lhs", "random"] | None = None
    variables: list[str] = Field(default_factory=list)
    variable: str | None = None
    metric: str | None = None
    pct: float | None = None
    start: float | None = None
    end: float | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    soft: dict[str, dict[str, float]] = Field(default_factory=dict)
    likelihood: dict[str, dict[str, float]] = Field(default_factory=dict)
    query: list[str] = Field(default_factory=list)
    over: list[str] = Field(default_factory=list)
    target: str | None = None
    state: str | None = None


class BuildSpec(_Spec):
    """Everything ``latris build`` adds, applied as one commit."""

    model_type: str | None = None  # view for polarity and roles; default: the project's first selected type
    context: SpecContext | None = None
    outcome: str | None = None  # factor the model explains (gets the outcome role)
    factors: list[SpecFactor] = Field(default_factory=list)
    links: list[SpecLink] = Field(default_factory=list)
    sources: list[SpecSource] = Field(default_factory=list)
    assumptions: list[str | SpecAssumption] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    findings: list[SpecFinding] = Field(default_factory=list)
    challenges: list[SpecChallenge] = Field(default_factory=list)
    decisions: list[SpecDecision] = Field(default_factory=list)
    interpretation: list[SpecInterpretation] = Field(default_factory=list)
    sd: SpecSD | None = None  # System Dynamics roles, values, equations, tables, uncertainty, scenarios
    bn: SpecBN | None = None  # Bayesian network states and probability tables
    analyses: list[SpecAnalysis] = Field(default_factory=list)  # run and recorded after building
