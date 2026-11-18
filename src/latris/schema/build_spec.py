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

from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    extends: str | None = None  # another scenario this one builds on (its values apply first)
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


class SpecBNScenario(_Spec):
    """A named what-if over the network. ``observe``/``set``: {factor: state}; ``soft``/``likelihood``:
    {factor: {state: value}}; ``tables``: 'Factor[Parent=state,…]=p1,p2,…' or 'Factor=p1,p2,…'."""

    name: str
    extends: str | None = None
    observe: dict[str, str] = Field(default_factory=dict)
    soft: dict[str, dict[str, float]] = Field(default_factory=dict)
    likelihood: dict[str, dict[str, float]] = Field(default_factory=dict)
    set: dict[str, str] = Field(default_factory=dict)
    tables: list[str] = Field(default_factory=list)
    description: str = ""
    reason: str = ""
    origin: ProvenanceOrigin | None = None
    source: str | None = None


class SpecBN(_Spec):
    states: list[SpecBNStates] = Field(default_factory=list)
    tables: list[SpecBNTable] = Field(default_factory=list)
    noisy_or: list[SpecNoisyOr] = Field(default_factory=list)
    uncertainty: list[SpecBNUncertainty] = Field(default_factory=list)
    scenarios: list[SpecBNScenario] = Field(default_factory=list)


# ── analyses ─────────────────────────────────────────────────────────
#
# One model per analysis kind, so each takes only its own options (a wrong option is refused, not
# ignored) and its JSON schema says exactly what it needs. ``SpecAnalysis`` is their union,
# discriminated by ``kind``. Adding an analysis: a model here, added to the union.


# What each analysis option means, wherever it appears (a kind's own field description wins). The JSON
# schemas apps and chat tools read carry these, so options are documented once.
ANALYSIS_OPTION_DOCS: dict[str, str] = {
    "settings": "The clock: initial_time, final_time, dt, saveper, method (euler | rk2 | rk4 | adaptive), "
                "time_units (e.g. 'month'). Missing keys come from the model's SD settings.",
    "apply_to_all": "Values that hold in every run, the baseline included (a 'world'), as 'Factor=value [units]'.",
    "scenarios": "Saved scenarios (options) to run or compare, by name.",
    "set": "Unsaved changes to try as one more scenario, as 'Factor=value [units]'.",
    "scenario": "A saved scenario to run on instead of the baseline.",
    "runs": "Number of sampled draws.",
    "seed": "Random seed; the same seed gives the same draws.",
    "sampling": "lhs (Latin hypercube, default) or random.",
    "variables": "Factors to report (default: the stocks).",
    "variable": "The factor whose result is measured.",
    "metric": "final | peak | peak-time | min | mean | total | at:T (the value at time T).",
    "reference": "The arm every option is measured against: 'baseline' or one of the options.",
    "pct": "Swing for values without an uncertainty range, in percent (default 10).",
    "start": "Start of the window to score (default: the whole run).",
    "end": "End of the window to score (default: the whole run).",
    "evidence": "Observed states, factor → state, e.g. {'Rain': 'yes'}.",
    "soft": "Uncertain observations, factor → {state: probability}: {'Wet': {'yes': 0.8}} makes P(Wet = yes) 80%.",
    "likelihood": "Relative weights for an observation, factor → {state: weight}.",
    "interventions": "Factors SET to a state (an option or policy), factor → state: what if we make it so.",
    "query": "Factors whose probabilities to report (default: all).",
    "over": "Factors the explanation covers (default: every unobserved factor).",
    "target": "The factor (or output) the result is about.",
    "state": "The state of target whose probability is the result.",
    "max_order": "List cut sets up to this order (default: all).",
    "treatment": "The factor whose effect is estimated.",
    "outcome": "The factor the effect is on.",
    "dataset": "A dataset registered with `latris data add`, by name.",
    "adjust": "Factors to adjust for (default: the smallest valid set the model identifies).",
    "columns": "Factor label → dataset column, where names differ.",
    "estimator": "auto | linear | logistic.",
    "time": "The dataset's time column (numbers or dates).",
    "at": "The first period the intervention could affect.",
    "group": "Difference-in-differences: the column saying which group a row is in.",
    "treated": "Difference-in-differences: the group value(s) that received the intervention.",
}


def _describe_options(schema: dict[str, Any], cls: Any = None) -> None:
    for name, prop in (schema.get("properties") or {}).items():
        if name in ANALYSIS_OPTION_DOCS and "description" not in prop:
            prop["description"] = ANALYSIS_OPTION_DOCS[name]


class _Analysis(_Spec):
    """An analysis to run (and record, so the report shows it) once the model is built."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, json_schema_extra=_describe_options)

    @model_validator(mode="before")
    @classmethod
    def _drop_empty_foreign_keys(cls, data: Any) -> Any:
        # Specs and links written before analyses were typed carried every option of every kind; an
        # empty one this kind doesn't take is dropped, a set one is still refused.
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k in cls.model_fields or v not in (None, {}, [], "")}
        return data


class _Settings(_Analysis):
    # initial_time, final_time, dt, saveper, method, time_units
    settings: dict[str, float | str] = Field(default_factory=dict)


class _World(_Settings):
    # values that hold in every run, the baseline included
    apply_to_all: list[str] = Field(default_factory=list)


class _Draws(_Analysis):
    runs: int | None = None
    seed: int | None = None
    sampling: Literal["lhs", "random"] | None = None


class _Evidence(_Analysis):
    evidence: dict[str, str] = Field(default_factory=dict)
    soft: dict[str, dict[str, float]] = Field(default_factory=dict)  # {node: {state: probability}} (certainty)
    likelihood: dict[str, dict[str, float]] = Field(default_factory=dict)  # {node: {state: weight}}


class _Target(_Analysis):
    target: str | None = None
    state: str | None = None


class SimulateAnalysis(_World):
    """System dynamics: simulate the baseline and saved scenarios; ``set`` is a what-if."""

    kind: Literal["simulate"]
    scenarios: list[str] = Field(default_factory=list)
    set: list[str] = Field(default_factory=list)


class MonteCarloAnalysis(_World, _Draws):
    """System dynamics: uncertainty bands from the ranges set on values."""

    kind: Literal["monte_carlo"]
    variables: list[str] = Field(default_factory=list)
    scenario: str | None = None


class CompareAnalysis(_World, _Draws):
    """System dynamics: options under uncertainty, on the same draws."""

    kind: Literal["compare"]
    scenarios: list[str] = Field(default_factory=list)
    variable: str | None = None
    metric: str | None = None
    reference: str | None = None  # the arm every option is measured against: 'baseline' or a compared scenario


class SensitivityAnalysis(_World):
    """System dynamics: which values move ``variable`` most."""

    kind: Literal["sensitivity"]
    variable: str | None = None
    metric: str | None = None
    pct: float | None = None
    scenario: str | None = None


class LoopsAnalysis(_Settings):
    """System dynamics: which feedback loop drives the behaviour (over ``start``–``end``)."""

    kind: Literal["loops"]
    scenario: str | None = None
    start: float | None = None
    end: float | None = None


class BnQueryAnalysis(_Evidence):
    """Bayesian network: the probability of each state of ``query`` (all factors if empty)."""

    kind: Literal["bn_query"]
    interventions: dict[str, str] = Field(default_factory=dict)  # factors SET to a state (do-operator)
    query: list[str] = Field(default_factory=list)
    scenario: str | None = None


class BnExplainAnalysis(_Evidence):
    """Bayesian network: the most likely combination of causes (over ``over``)."""

    kind: Literal["bn_explain"]
    over: list[str] = Field(default_factory=list)


class BnMonteCarloAnalysis(_Evidence, _Target):
    """Bayesian network: how sure P(target = state) is, given how well each table is known."""

    kind: Literal["bn_monte_carlo"]
    runs: int | None = None
    seed: int | None = None
    scenario: str | None = None


class BnCompareAnalysis(_Evidence, _Target):
    """Bayesian network: options (BN scenarios) on the same table draws."""

    kind: Literal["bn_compare"]
    scenarios: list[str] = Field(default_factory=list)
    reference: str | None = None
    runs: int | None = None
    seed: int | None = None


class BnSensitivityAnalysis(_Target):
    """Bayesian network: which table entries move P(target = state) most."""

    kind: Literal["bn_sensitivity"]
    evidence: dict[str, str] = Field(default_factory=dict)


class TocCheckAnalysis(_Analysis):
    """Theory of change: pathways and their evidence."""

    kind: Literal["toc_check"]


class TocTraceAnalysis(_Analysis):
    """Theory of change: process tracing — each link's posterior from its tests, pathway confidence."""

    kind: Literal["toc_trace"]


class TocImpactAnalysis(_Analysis):
    """Theory of change: impact on ``outcome`` from a dataset — interrupted time series, or
    difference-in-differences with ``group`` and ``treated``."""

    kind: Literal["toc_impact"]
    outcome: str | None = None
    dataset: str | None = None
    time: str | None = None  # the dataset's time column (numbers or dates)
    at: str | float | None = None  # the first period the intervention could affect
    group: str | None = None  # difference-in-differences: the column saying which group a row is in
    treated: list[str] = Field(default_factory=list)  # … and the group value(s) that received it
    columns: dict[str, str] = Field(default_factory=dict)  # factor label → dataset column, where names differ


class FtAnalyseAnalysis(_Analysis):
    """Fault tree: cut sets (up to ``max_order``), top-event probability and importance."""

    kind: Literal["ft_analyse"]
    max_order: int | None = Field(default=None, ge=1)


class BowtieAnalyseAnalysis(_Analysis):
    """Bow-tie: lines, barrier flags and frequencies."""

    kind: Literal["bowtie_analyse"]


class EtAnalyseAnalysis(_Analysis):
    """Event tree: sequences and end states."""

    kind: Literal["et_analyse"]


class RiskMonteCarloAnalysis(_Draws):
    """Fault tree, bow-tie or event tree: uncertainty in the top-event probability or the frequencies;
    ``target`` is the output to headline."""

    kind: Literal["ft_monte_carlo", "bowtie_monte_carlo", "et_monte_carlo"]
    target: str | None = None


class DagEstimateAnalysis(_Analysis):
    """DAG: the effect of ``treatment`` on ``outcome`` from a registered dataset."""

    kind: Literal["dag_estimate"]
    treatment: str | None = None
    outcome: str | None = None
    dataset: str | None = None
    adjust: list[str] = Field(default_factory=list)  # empty: the smallest valid set of measured factors
    columns: dict[str, str] = Field(default_factory=dict)  # factor label → dataset column, where names differ
    estimator: Literal["auto", "linear", "logistic"] | None = None


class McdaAnalyseAnalysis(_Analysis):
    """MCDA: ranking and weight sensitivity."""

    kind: Literal["mcda_analyse"]


class AchAnalyseAnalysis(_Analysis):
    """ACH: competing hypotheses ranked, linchpins."""

    kind: Literal["ach_analyse"]


class DtAnalyseAnalysis(_Analysis):
    """Decision tree: best strategy, EVPI, probability thresholds."""

    kind: Literal["dt_analyse"]


class MarkovAnalyseAnalysis(_Analysis):
    """Markov cohort: costs, outcomes, incremental cost-effectiveness."""

    kind: Literal["markov_analyse"]


ANALYSIS_MODELS: tuple[type[_Analysis], ...] = (
    SimulateAnalysis, MonteCarloAnalysis, CompareAnalysis, SensitivityAnalysis, LoopsAnalysis,
    BnQueryAnalysis, BnExplainAnalysis, BnMonteCarloAnalysis, BnCompareAnalysis, BnSensitivityAnalysis,
    TocCheckAnalysis, TocTraceAnalysis, TocImpactAnalysis, FtAnalyseAnalysis, BowtieAnalyseAnalysis,
    EtAnalyseAnalysis, RiskMonteCarloAnalysis, DagEstimateAnalysis, McdaAnalyseAnalysis, AchAnalyseAnalysis,
    DtAnalyseAnalysis, MarkovAnalyseAnalysis,
)

SpecAnalysis = Annotated[
    SimulateAnalysis | MonteCarloAnalysis | CompareAnalysis | SensitivityAnalysis | LoopsAnalysis
    | BnQueryAnalysis | BnExplainAnalysis | BnMonteCarloAnalysis | BnCompareAnalysis | BnSensitivityAnalysis
    | TocCheckAnalysis | TocTraceAnalysis | TocImpactAnalysis | FtAnalyseAnalysis | BowtieAnalyseAnalysis
    | EtAnalyseAnalysis | RiskMonteCarloAnalysis | DagEstimateAnalysis | McdaAnalyseAnalysis | AchAnalyseAnalysis
    | DtAnalyseAnalysis | MarkovAnalyseAnalysis,
    Field(discriminator="kind"),
]


def analysis_model(kind: str) -> type[_Analysis]:
    """The model for one analysis kind (KeyError if there's none)."""
    for m in ANALYSIS_MODELS:
        if kind in get_args(m.model_fields["kind"].annotation):
            return m
    raise KeyError(kind)


def analysis_kinds() -> tuple[str, ...]:
    """Every analysis kind a spec can name."""
    return tuple(k for m in ANALYSIS_MODELS for k in get_args(m.model_fields["kind"].annotation))


def make_analysis(**fields: Any) -> SpecAnalysis:
    """An analysis of ``fields["kind"]``, validated against that kind's model."""
    return analysis_model(fields["kind"]).model_validate(fields)


class SpecCarriedResult(_Spec):
    """A recorded result a link carries as the sender's, because it can't be re-run where the link opens: it
    read a dataset, and links don't carry data. Written by ``latris link`` / ``export spec``, not by hand.

    The payload names factors and links by label (``{{node:Label}}``, ``{{link:From -> To}}``); the build maps
    them to this project's ids. The report shows it as computed by the sender, with the datasets it read.
    """

    kind: str  # the result kind, e.g. "dag-estimate"
    model_type: str
    key: str  # which runs count as the same analysis
    summary: str = ""
    purpose: str = "other"
    algorithm: str = ""
    library_version: str = ""
    datasets: list[dict[str, str]] = Field(default_factory=list)  # each dataset it read: name, sha256
    payload: dict[str, Any]


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
    # results that read a dataset: carried as the sender's, recorded after the analyses
    carried_results: list[SpecCarriedResult] = Field(default_factory=list)
