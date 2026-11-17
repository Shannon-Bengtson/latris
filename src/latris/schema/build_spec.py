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
    exclusions: str | None = None  # what was left out and why
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


class SpecToCLevel(_Spec):
    node: str
    level: Literal["input", "activity", "output", "short_term_outcome", "long_term_outcome", "impact"]


class SpecToCPrior(_Spec):
    """Process tracing: confidence that a link holds before the tests."""

    link: str  # "From -> To"
    prior: float = Field(gt=0.0, lt=1.0)
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecToCTest(_Spec):
    """Process tracing: one evidence test on a link — P(evidence | link holds), P(evidence | it doesn't), found?"""

    link: str  # "From -> To"
    name: str
    p_if_true: float = Field(gt=0.0, lt=1.0)
    p_if_false: float = Field(gt=0.0, lt=1.0)
    found: bool | None = None  # omit: not looked for yet
    description: str | None = None
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecToC(_Spec):
    """Theory-of-change levels, plus process-tracing priors and tests on its links.

    The spec's ``outcome`` (if any) becomes an impact.
    """

    levels: list[SpecToCLevel] = Field(default_factory=list)
    priors: list[SpecToCPrior] = Field(default_factory=list)
    tests: list[SpecToCTest] = Field(default_factory=list)


class SpecFTEvent(_Spec):
    node: str
    type: Literal["top_event", "intermediate_event", "basic_event", "undeveloped_event"]


class SpecFTGate(_Spec):
    node: str
    gate: Literal["and", "or", "vote"]
    k: int | None = Field(default=None, ge=1)


class SpecFTProbability(_Spec):
    node: str
    probability: float = Field(ge=0.0, le=1.0)
    source: str | None = None  # where it came from (a reference key, dataset, …)
    origin: ProvenanceOrigin | None = None
    verified: bool = False  # a person has checked it against its source
    notes: str | None = None


class SpecRiskUncertainty(_SpecParam):
    """How uncertain a risk model's number is, for Monte Carlo: a fault-tree event's probability, a bow-tie
    barrier's PFD or threat's frequency, an event-tree heading's P(yes) (``given`` its condition, as in the
    probability entry) or initiating frequency.

    ``params`` as for the distribution, or ``{median, error_factor}`` for a lognormal.
    """

    node: str
    distribution: Literal["uniform", "triangular", "normal", "lognormal", "beta", "gamma"]
    params: dict[str, float]
    given: dict[str, Literal["yes", "no"]] = Field(default_factory=dict)  # event trees only
    reason: str = ""
    verified: bool = False


class SpecFT(_Spec):
    """Fault tree: event types, gates on top/intermediate events, basic-event probabilities.

    The spec's ``outcome`` (if any) becomes the top event.
    """

    events: list[SpecFTEvent] = Field(default_factory=list)
    gates: list[SpecFTGate] = Field(default_factory=list)
    probabilities: list[SpecFTProbability] = Field(default_factory=list)
    uncertainty: list[SpecRiskUncertainty] = Field(default_factory=list)


class SpecBTElement(_Spec):
    node: str
    type: Literal["hazard", "top_event", "threat", "consequence", "barrier", "escalation_factor"]


class SpecBTBarrier(_Spec):
    node: str
    type: Literal["passive_hardware", "active_hardware", "active_hardware_human", "human"] | None = None
    status: Literal["in_place", "degraded", "not_in_place"] = "in_place"
    owner: str | None = None
    pfd: float | None = Field(default=None, ge=0.0, le=1.0)  # probability of failure on demand
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False
    notes: str | None = None


class SpecBTFrequency(_Spec):
    node: str
    frequency: float = Field(ge=0.0)  # per year
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False
    notes: str | None = None


class SpecBowTie(_Spec):
    """Bow-tie elements, barriers and threat frequencies. The spec's ``outcome`` becomes the top event."""

    elements: list[SpecBTElement] = Field(default_factory=list)
    barriers: list[SpecBTBarrier] = Field(default_factory=list)
    frequencies: list[SpecBTFrequency] = Field(default_factory=list)
    uncertainty: list[SpecRiskUncertainty] = Field(default_factory=list)


class SpecETElement(_Spec):
    node: str
    type: Literal["initiating_event", "functional_event", "end_state"]


class SpecETSequence(_Spec):
    answers: dict[str, Literal["yes", "no"]] = Field(default_factory=dict)  # heading label → answer
    end_state: str


class SpecETProbability(_Spec):
    node: str  # a heading
    p_yes: float = Field(ge=0.0, le=1.0)
    given: dict[str, Literal["yes", "no"]] = Field(default_factory=dict)  # earlier answers it applies under
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False
    notes: str | None = None


class SpecETFrequency(_Spec):
    node: str  # the initiating event
    frequency: float = Field(ge=0.0)  # per year
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False
    notes: str | None = None


class SpecEventTree(_Spec):
    """Event tree: elements, heading order, sequences, branch probabilities, initiating frequency."""

    elements: list[SpecETElement] = Field(default_factory=list)
    order: list[str] = Field(default_factory=list)  # heading labels, left to right
    sequences: list[SpecETSequence] = Field(default_factory=list)
    probabilities: list[SpecETProbability] = Field(default_factory=list)
    frequency: SpecETFrequency | None = None
    uncertainty: list[SpecRiskUncertainty] = Field(default_factory=list)


class SpecMCDAElement(_Spec):
    node: str
    type: Literal["option", "criterion"]


class SpecMCDACriterion(_Spec):
    node: str
    weight: float | None = Field(default=None, gt=0)  # swing weight; normalised over the criteria
    direction: Literal["higher", "lower"] | None = None  # which way is better
    worst: float | None = None  # the scale; omit both to use the options' range
    best: float | None = None
    units: str | None = None
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecMCDAScore(_Spec):
    option: str
    criterion: str
    value: float
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecMCDA(_Spec):
    """Multi-criteria decision analysis: options, criteria (weight, direction, scale) and scores."""

    elements: list[SpecMCDAElement] = Field(default_factory=list)
    criteria: list[SpecMCDACriterion] = Field(default_factory=list)
    scores: list[SpecMCDAScore] = Field(default_factory=list)


class SpecACHElement(_Spec):
    node: str
    type: Literal["hypothesis", "evidence_item"]


class SpecACHItem(_Spec):
    node: str
    credibility: Literal["high", "medium", "low"] = "medium"
    relevance: Literal["high", "medium", "low"] = "medium"
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecACHRating(_Spec):
    item: str
    hypothesis: str
    rating: Literal["CC", "C", "N", "I", "II"]
    rationale: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecACH(_Spec):
    """Analysis of competing hypotheses: hypotheses, evidence items (credibility, relevance) and ratings."""

    elements: list[SpecACHElement] = Field(default_factory=list)
    items: list[SpecACHItem] = Field(default_factory=list)
    ratings: list[SpecACHRating] = Field(default_factory=list)


class SpecDTNode(_Spec):
    node: str
    type: Literal["decision", "chance", "terminal"]


class SpecDTBranch(_Spec):
    link: str  # "Parent -> Child" (the link must exist under links)
    label: str | None = None  # the option or the state; default: the child's label
    probability: float | None = Field(default=None, ge=0.0, le=1.0)  # branches from a chance node
    value: float | None = None  # incurred along the branch (e.g. a cost, negative)
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecDTPayoff(_Spec):
    node: str  # a terminal node
    value: float
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecDTUncertainty(_Spec):
    node: str  # a chance node
    name: str  # chance nodes with the same name are one uncertainty (priced together for EVPI)


class SpecDT(_Spec):
    """Decision tree: node types, branches (label, probability, value), payoffs, uncertainties, objective."""

    objective: Literal["maximise", "minimise"] | None = None
    units: str | None = None
    elements: list[SpecDTNode] = Field(default_factory=list)
    branches: list[SpecDTBranch] = Field(default_factory=list)
    payoffs: list[SpecDTPayoff] = Field(default_factory=list)
    uncertainties: list[SpecDTUncertainty] = Field(default_factory=list)


class SpecMarkovElement(_Spec):
    node: str
    type: Literal["state", "strategy"]


class SpecMarkovTransition(_Spec):
    link: str  # "From state -> To state" (the link must exist under links)
    probability: float = Field(ge=0.0, le=1.0)  # per cycle
    strategy: str | None = None  # this strategy only; omit for every strategy
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecMarkovReward(_Spec):
    state: str
    strategy: str | None = None
    cost: float | None = None  # per cycle
    utility: float | None = None  # per year (e.g. a quality-of-life weight)
    notes: str | None = None
    source: str | None = None
    origin: ProvenanceOrigin | None = None
    verified: bool = False


class SpecMarkovStart(_Spec):
    state: str
    proportion: float = Field(ge=0.0, le=1.0)


class SpecMarkovSettings(_Spec):
    cycle_length: float | None = Field(default=None, gt=0)
    num_cycles: int | None = Field(default=None, ge=1)
    time_units: Literal["days", "weeks", "months", "years"] | None = None
    discount_rate: float | None = Field(default=None, ge=0, le=1)
    outcome_discount_rate: float | None = Field(default=None, ge=0, le=1)
    half_cycle_correction: bool | None = None
    wtp: float | None = Field(default=None, ge=0)
    cost_units: str | None = None
    outcome_units: str | None = None


class SpecMarkov(_Spec):
    """Markov cohort model: states and strategies, transitions, costs and utilities, the start, settings."""

    elements: list[SpecMarkovElement] = Field(default_factory=list)
    settings: SpecMarkovSettings | None = None
    transitions: list[SpecMarkovTransition] = Field(default_factory=list)
    rewards: list[SpecMarkovReward] = Field(default_factory=list)
    start: list[SpecMarkovStart] = Field(default_factory=list)


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
    | bn_sensitivity (target, state, evidence) | toc_check (theory-of-change pathways; no options)
    | toc_trace (process tracing: each link's posterior from its tests, pathway confidence; no options)
    | ft_monte_carlo / bowtie_monte_carlo / et_monte_carlo (uncertainty in the top-event probability or the
      frequencies: runs, seed, sampling; target: the output to headline)
    | toc_impact (interrupted time series, or difference-in-differences with group and treated: outcome,
      dataset, time, at, group, treated, columns)
    | ft_analyse (fault-tree cut sets, probability and importance; max_order)
    | bowtie_analyse (bow-tie lines, barrier flags and frequencies; no options)
    | et_analyse (event-tree sequences and end states; no options)
    | dag_estimate (effect of treatment on outcome from a dataset: treatment, outcome, dataset, adjust,
      columns, estimator) | mcda_analyse (ranking and weight sensitivity; no options)
    | ach_analyse (competing hypotheses: ranking, linchpins; no options)
    | dt_analyse (decision tree: best strategy, EVPI, probability thresholds; no options)
    | markov_analyse (Markov cohort: costs, outcomes, incremental cost-effectiveness; no options).
    ``soft`` is {node: {state: probability}} (certainty); ``likelihood`` {node: {state: weight}}.
    ``settings``: initial_time, final_time, dt, saveper, method, time_units.
    """

    kind: Literal[
        "simulate", "monte_carlo", "sensitivity", "loops", "bn_query", "bn_explain", "bn_monte_carlo",
        "bn_sensitivity", "toc_check", "ft_analyse", "bowtie_analyse", "et_analyse", "dag_estimate",
        "mcda_analyse", "ach_analyse", "dt_analyse", "markov_analyse", "toc_trace", "toc_impact",
        "ft_monte_carlo", "bowtie_monte_carlo", "et_monte_carlo",
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
    max_order: int | None = Field(default=None, ge=1)  # ft_analyse: list cut sets up to this order
    # dag_estimate: the effect of treatment on outcome, from a registered dataset
    treatment: str | None = None
    outcome: str | None = None
    dataset: str | None = None
    adjust: list[str] = Field(default_factory=list)  # empty: the smallest valid set of measured factors
    columns: dict[str, str] = Field(default_factory=dict)  # factor label → dataset column, where names differ
    estimator: Literal["auto", "linear", "logistic"] | None = None
    # toc_impact: interrupted time series (no group) or difference-in-differences, for outcome from dataset
    time: str | None = None  # the dataset's time column (numbers or dates)
    at: str | float | None = None  # the first period the intervention could affect
    group: str | None = None  # difference-in-differences: the column saying which group a row is in
    treated: list[str] = Field(default_factory=list)  # … and the group value(s) that received it


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
    toc: SpecToC | None = None  # Theory of Change levels (input … impact)
    ft: SpecFT | None = None  # Fault tree events, gates and probabilities
    bowtie: SpecBowTie | None = None  # Bow-tie elements, barriers and threat frequencies
    event_tree: SpecEventTree | None = None  # Event tree elements, order, sequences, probabilities
    mcda: SpecMCDA | None = None  # MCDA options, criteria and scores
    ach: SpecACH | None = None  # ACH hypotheses, evidence items and ratings
    decision_tree: SpecDT | None = None  # Decision tree nodes, branches, payoffs, uncertainties
    markov: SpecMarkov | None = None  # Markov states, strategies, transitions, rewards, start, settings
    analyses: list[SpecAnalysis] = Field(default_factory=list)  # run and recorded after building
