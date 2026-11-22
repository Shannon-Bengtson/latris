"""The methods-and-foundations registry — one source of truth for what Latris implements.

Every entry names an established method Latris actually implements, the
literature it stands on, what it is used for, and its stated limits. Three
surfaces read this one registry so they cannot drift apart:

- the report's **Methods and foundations** section (:func:`render_methods_section`),
- the capability manifest's ``foundations`` block (``latris capabilities --json``),
- ``latris foundations`` (``latris foundations --json`` for the raw list).

``docs/FOUNDATIONS.md`` is the prose companion; the registry and the code it
describes win where the two disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import EvidenceLinkSet, ProjectFoundation, ReferenceLibrary


@dataclass(frozen=True)
class Foundation:
    """One implemented method, its citation, and its stated limits.

    ``applies_to`` holds model-type ids from ``schema/model_types.py`` — or
    ``("*",)`` for the evidence discipline, which spans every model type.
    """

    id: str
    applies_to: tuple[str, ...]
    method: str
    citation: str
    used_for: str
    limits: str | None


FOUNDATIONS: tuple[Foundation, ...] = (
    Foundation(
        id="cld-loop-analysis",
        applies_to=("cld",),
        method="Qualitative loop analysis (causal loop diagrams)",
        citation="Sterman (2000), *Business Dynamics*, ch. 4; Meadows (2008), *Thinking in Systems*",
        used_for=(
            "detecting feedback loops, classifying them balancing or reinforcing by polarity, "
            "and propagating qualitative effects along paths"
        ),
        limits=(
            "Ambiguous polarity (~) is reported as unknown, not guessed; loop enumeration "
            "is capped and raises beyond it."
        ),
    ),
    Foundation(
        id="dag-identification",
        applies_to=("dag",),
        method="Causal identification on a DAG",
        citation=(
            "Pearl (2009), *Causality*; Hernán & Robins (2020), "
            "*Causal Inference: What If*; d-separation after Shachter (1998)"
        ),
        used_for=(
            "d-separation queries, Markov blankets, path enumeration, and backdoor "
            "adjustment sets by graph surgery"
        ),
        limits=(
            "Identification: says what must be adjusted for, not how big the effect is (that is the separate "
            "effect estimate); no counterfactuals; minimal adjustment sets are enumerated only up to size 3."
        ),
    ),
    Foundation(
        id="dag-estimation",
        applies_to=("dag",),
        method="Effect estimation by backdoor adjustment",
        citation=(
            "Pearl (2009), *Causality*, the back-door adjustment; Hernán & Robins (2020), *Causal Inference: "
            "What If*, ch. 15 (outcome regression); MacKinnon & White (1985), HC3 standard errors; Seabold & "
            "Perktold (2010), statsmodels"
        ),
        used_for=(
            "the average effect of one factor on another from a dataset: the smallest valid backdoor set made "
            "only of measured factors (or a given set, checked against the DAG), linear regression with robust "
            "standard errors or logistic regression for a yes/no outcome, beside the unadjusted association"
        ),
        limits=(
            "Causal only under the DAG's assumptions (no common cause left out), the model's linear, additive "
            "form, and positivity; complete cases only; one numeric or two-valued treatment, no effect "
            "modification; refuses rather than estimates when every valid adjustment set needs an unmeasured "
            "factor."
        ),
    ),
    Foundation(
        id="bn-exact-inference",
        applies_to=("bn",),
        method="Exact inference in discrete Bayesian networks",
        citation=(
            "Pearl (1988), *Probabilistic Reasoning in Intelligent Systems*; "
            "Fenton & Neil (2018), *Risk Assessment and Decision Analysis with "
            "Bayesian Networks* (2nd ed.); Jeffrey (1965), *The Logic of Decision* "
            "(soft evidence)"
        ),
        used_for=(
            "per-node posterior marginals by variable elimination, soft "
            "(likelihood) evidence per node, and MAP/MPE explanations"
        ),
        limits="Variable elimination only — no junction tree or belief propagation; marginals, not joints.",
    ),
    Foundation(
        id="bn-parameter-learning",
        applies_to=("bn",),
        method="CPT parameter learning from data",
        citation=(
            "Fenton & Neil (2018), *Risk Assessment and Decision Analysis with "
            "Bayesian Networks* (2nd ed.)"
        ),
        used_for="MLE and Bayesian-Dirichlet estimators with human-elicited CPT rows protected from overwrite",
        limits="CPT parameters only — structure learning is excluded by design.",
    ),
    Foundation(
        id="fcm-steady-state",
        applies_to=("fcm",),
        method="Fuzzy cognitive map inference",
        citation='Kosko (1986), "Fuzzy Cognitive Maps", *Int. J. Man-Machine Studies* 24(1)',
        used_for=(
            "weighted matrix iteration to a steady state with sigmoid, tanh, or step "
            "transfer functions and clamped scenario nodes"
        ),
        limits="Fixed-point only — non-convergence is flagged; limit cycles are not analysed.",
    ),
    Foundation(
        id="ft-analysis",
        applies_to=("fault_tree",),
        method="Fault tree analysis",
        citation=(
            "Vesely, Goldberg, Roberts & Haasl (1981), *Fault Tree Handbook* (NUREG-0492); IEC 61025:2006; "
            'Rauzy (1993), "New Algorithms for Fault Trees Analysis", *Reliability Engineering & System '
            'Safety* 40(3); Birnbaum (1969); Fussell (1975)'
        ),
        used_for=(
            "AND, OR and k-out-of-n gates; minimal cut sets and single points of failure; the exact "
            "top-event probability from a binary decision diagram (with the rare-event approximation and "
            "min-cut upper bound beside it); Birnbaum, Fussell–Vesely and risk-achievement-worth importance"
        ),
        limits=(
            "Static and coherent: basic events are assumed independent (no common-cause model), there are "
            "no NOT, priority-AND or sequence gates, and probabilities are point values with no "
            "uncertainty propagation; cut sets are listed up to 20,000."
        ),
    ),
    Foundation(
        id="bt-barriers",
        applies_to=("bow_tie",),
        method="Bow-tie barrier analysis with layer-of-protection estimates",
        citation=(
            "CCPS & Energy Institute (2018), *Bow Ties in Risk Management: A Concept Book for Process Safety*; "
            "CCPS (2001), *Layer of Protection Analysis: Simplified Process Risk Assessment*"
        ),
        used_for=(
            "threat and consequence lines through prevention and mitigation barriers, escalation factors and "
            "their controls, the CCPS barrier types; flags for lines resting on one effective barrier or none, "
            "barriers shared between lines, uncontrolled escalation and barriers with no owner; with threat "
            "frequencies and barrier failure probabilities, the top-event and consequence frequencies and how "
            "much each barrier buys"
        ),
        limits=(
            "Barriers are assumed to fail independently (shared barriers are flagged, and counted once per "
            "threat); frequencies and failure probabilities are point values at the order-of-magnitude "
            "precision of LOPA; escalation factors are not quantified and there is no consequence severity "
            "or risk matrix."
        ),
    ),
    Foundation(
        id="et-analysis",
        applies_to=("event_tree",),
        method="Event tree analysis",
        citation=(
            "IEC 62502:2010, *Event tree analysis (ETA)*; US NRC (1983), *PRA Procedures Guide* (NUREG/CR-2300); "
            "US NRC (1975), *Reactor Safety Study* (WASH-1400)"
        ),
        used_for=(
            "sequences from one initiating event through ordered yes/no headings to end states; a check that the "
            "sequences cover every branch exactly once; sequence probabilities as products of branch "
            "probabilities (conditional on earlier answers where given), end-state totals and, with the "
            "initiating frequency, frequencies per year"
        ),
        limits=(
            "Binary branches only; dependence between headings only as explicitly stated conditional "
            "probabilities; point values with no uncertainty propagation; heading probabilities are entered, "
            "not linked live to fault trees."
        ),
    ),
    Foundation(
        id="mcda-additive-value",
        applies_to=("mcda",),
        method="Multi-criteria decision analysis (additive value model)",
        citation=(
            "Keeney & Raiffa (1976), *Decisions with Multiple Objectives*; Belton & Stewart (2002), "
            "*Multiple Criteria Decision Analysis*; UK DCLG (2009), *Multi-criteria analysis: a manual*"
        ),
        used_for=(
            "options' scores turned into 0–1 values on linear scales, combined by normalised swing weights; the "
            "ranking with each criterion's contribution, dominated options, and for each weight the nearest "
            "values (others keeping their proportions) at which the top choice changes"
        ),
        limits=(
            "Additive and linear: assumes the criteria are preferentially independent and value is linear "
            "between worst and best; weights are judgements and mean nothing apart from their scales; scales "
            "taken from the options' range change when an option is added; one-way weight sensitivity only, "
            "no probabilistic weights or scores, and no AHP or outranking methods."
        ),
    ),
    Foundation(
        id="ach-heuer",
        applies_to=("ach",),
        method="Analysis of competing hypotheses",
        citation=(
            "Heuer (1999), *Psychology of Intelligence Analysis*, ch. 8; Heuer & Pherson (2015), *Structured "
            "Analytic Techniques for Intelligence Analysis*"
        ),
        used_for=(
            "every evidence item rated against every hypothesis (CC to II) with its reasoning; hypotheses ranked "
            "by credibility- and relevance-weighted inconsistency — the least evidence against, not the most "
            "for; evidence that doesn't discriminate; linchpin items without which the lead changes or ties, with "
            "whether their sources were checked"
        ),
        limits=(
            "Ratings and weights are judgements; the weights (high 1.0, medium 0.7, low 0.4; an inconsistency "
            "1, a strong one 2) are Latris's stated convention, not Heuer's; items are treated as independent "
            "and no probabilities are computed — the ranking orders hypotheses, it doesn't say how likely each is."
        ),
    ),
    Foundation(
        id="dt-expected-value",
        applies_to=("decision_tree",),
        method="Decision trees and the value of information",
        citation=(
            "Raiffa (1968), *Decision Analysis*; Clemen & Reilly (2014), *Making Hard Decisions*, 3rd ed.; "
            "Howard (1966), \"Information Value Theory\", *IEEE Trans. Systems Science and Cybernetics* 2(1)"
        ),
        used_for=(
            "rolling back expected values to the optimal strategy; the expected value of perfect information for "
            "each uncertainty (grouping chance nodes that resolve the same uncertainty under different choices) "
            "and for all of them together; the probabilities at which the best first choice changes"
        ),
        limits=(
            "Risk-neutral (expected value, no utility function); point probabilities and payoffs (ranges on "
            "them go through the probabilistic sensitivity analysis); EVPI needs an uncertainty to have the same "
            "probabilities whatever is chosen, and treats separate uncertainties as independent; no imperfect "
            "information (EVSI); thresholds for two-state uncertainties only."
        ),
    ),
    Foundation(
        id="markov-cohort",
        applies_to=("markov",),
        method="Cohort Markov model and incremental cost-effectiveness analysis",
        citation=(
            "Sonnenberg & Beck (1993), \"Markov Models in Medical Decision Making\", *Medical Decision Making* "
            "13(4); Briggs, Claxton & Sculpher (2006), *Decision Modelling for Health Economic Evaluation*; "
            "Drummond et al. (2015), *Methods for the Economic Evaluation of Health Care Programmes*, 4th ed."
        ),
        used_for=(
            "a cohort moving between states each cycle (per-strategy transition probabilities, the rest staying); "
            "discounted costs and outcomes with optional half-cycle correction; incremental analysis — "
            "dominance, extended dominance, ICERs along the frontier — and net monetary benefit at a "
            "willingness to pay"
        ),
        limits=(
            "Memoryless: the chance of moving depends only on the current state, not on time in it (no tunnel "
            "states or time-varying probabilities yet); point estimates (ranges on them go through the "
            "probabilistic sensitivity analysis); a cohort expectation, not individual-level simulation."
        ),
    ),
    Foundation(
        id="decision-psa",
        applies_to=("decision_tree", "markov"),
        method="Probabilistic sensitivity analysis, acceptability curves and the value of information",
        citation=(
            "Briggs, Claxton & Sculpher (2006), *Decision Modelling for Health Economic Evaluation*, ch. 4–7; "
            "Fenwick, Claxton & Sculpher (2001), \"Representing uncertainty: the role of cost-effectiveness "
            "acceptability curves\", *Health Economics* 10(8); Claxton (1999), \"The irrelevance of inference\", "
            "*Journal of Health Economics* 18(3); McKay, Beckman & Conover (1979), *Technometrics* 21(2)"
        ),
        used_for=(
            "sampling every decision-tree payoff, branch value and probability, or Markov transition, cost and "
            "utility given a range (beta and gamma by mean and sd, Dirichlet sets of probabilities), seeded Latin "
            "hypercube; how often each choice is best; Markov acceptability curves and the expected value of "
            "perfect information over a willingness-to-pay grid; Spearman rank correlation for what drives the "
            "decision"
        ),
        limits=(
            "Inputs are sampled independently (no correlation between ranges); EVPI is for all parameters "
            "together — no partial EVPI (EVPPI) or sample information (EVSI); probabilities of leaving a Markov "
            "state sampled separately are scaled down when they sum past 1 (the report counts the runs)."
        ),
    ),
    Foundation(
        id="global-sensitivity",
        applies_to=("fault_tree", "bow_tie", "event_tree", "decision_tree", "markov", "sd"),
        method="Global sensitivity analysis: Sobol indices and Morris screening",
        citation=(
            "Saltelli et al. (2008), *Global Sensitivity Analysis: The Primer*; Sobol (2001), *Mathematics and "
            "Computers in Simulation* 55; Saltelli et al. (2010), *Computer Physics Communications* 181(2); "
            "Jansen (1999), *Computer Physics Communications* 117; Morris (1991), *Technometrics* 33(2); "
            "Campolongo, Cariboni & Saltelli (2007), *Environmental Modelling & Software* 22(10)"
        ),
        used_for=(
            "apportioning the variance of a result among every input with a range, varied together over their "
            "distributions: first-order and total Sobol indices (Saltelli and Jansen estimators on a scrambled "
            "Sobol sequence, bootstrap intervals), or Morris elementary effects (μ*, σ) as a cheaper screen"
        ),
        limits=(
            "Inputs are independent (no correlated ranges); Dirichlet sets of probabilities are held at their "
            "point values; indices are estimates — with heavy-tailed inputs or few samples they can stray below "
            "0 or above 1 (the intervals say how far to trust them); Morris effects are per unit of an input's "
            "quantile, comparable within one result only."
        ),
    ),
    Foundation(
        id="toc-results-chain",
        applies_to=("theory_of_change",),
        method="Theory of change as a results chain",
        citation=(
            'Weiss (1995), "Nothing as Practical as Good Theory", in Connell et al. (eds), *New Approaches '
            'to Evaluating Community Initiatives*; W.K. Kellogg Foundation (2004), *Logic Model Development '
            'Guide*; Mayne (2012), "Contribution Analysis: Coming of Age?", *Evaluation* 18(3)'
        ),
        used_for=(
            "logic-model levels (input, activity, output, short- and long-term outcome, impact), every "
            "pathway from an activity to an impact, and for each link its sources for and against, whether "
            "they were checked, and the assumptions stated for it"
        ),
        limits=(
            "Structural and evidential only — it shows where a results chain is unsupported, not how large "
            "an effect is or how much of an outcome the intervention caused; pathways are enumerated up to 200."
        ),
    ),
    Foundation(
        id="risk-monte-carlo",
        applies_to=("fault_tree", "bow_tie", "event_tree"),
        method="Monte Carlo propagation of parameter uncertainty in risk models",
        citation=(
            "US Nuclear Regulatory Commission (1983), *PRA Procedures Guide* (NUREG/CR-2300), ch. 12 (uncertainty, "
            "lognormal error factors); Apostolakis (1990), \"The Concept of Probability in Safety Assessments of "
            "Technological Systems\", *Science* 250; McKay, Beckman & Conover (1979), Latin hypercube sampling; "
            "Helton & Davis (2003), \"Latin hypercube sampling and the propagation of uncertainty in analyses of "
            "complex systems\", *Reliability Engineering & System Safety* 81"
        ),
        used_for=(
            "how sure a fault tree's top-event probability, a bow-tie's frequencies or an event tree's end-state "
            "frequencies are: a distribution (or a lognormal median and error factor) on each uncertain input, "
            "seeded Latin hypercube sampling through the model's own calculation, percentiles and the mean against "
            "the point estimate, and Spearman rank correlation for what drives the spread"
        ),
        limits=(
            "Inputs are sampled independently, except that each input takes one value per run wherever it appears "
            "(state-of-knowledge dependence within a model); no correlation between different inputs. Inputs "
            "without a range are treated as exact, so the spread is a lower bound. Rank correlation measures "
            "monotone influence only."
        ),
    ),
    Foundation(
        id="toc-impact",
        applies_to=("theory_of_change",),
        method="Impact estimation: interrupted time series and difference-in-differences",
        citation=(
            "Wagner, Soumerai, Zhang & Ross-Degnan (2002), \"Segmented regression analysis of interrupted time "
            "series studies\", *J Clin Pharm Ther* 27(4); Bernal, Cummins & Gasparrini (2017), \"Interrupted time "
            "series regression for the evaluation of public health interventions\", *Int J Epidemiol* 46(1); "
            "Angrist & Pischke (2009), *Mostly Harmless Econometrics*, ch. 5; Bertrand, Duflo & Mullainathan "
            "(2004), \"How Much Should We Trust Differences-in-Differences Estimates?\", *QJE* 119(1); Prais & "
            "Winsten (1954), AR(1) errors; Seabold & Perktold (2010), statsmodels"
        ),
        used_for=(
            "the change in a theory-of-change outcome when the intervention started: with no comparison group, "
            "segmented regression (step and change of slope, AR(1) errors, the effect by the last period "
            "against the projected pre-period trend); with one, difference-in-differences (cluster-robust errors "
            "with 20 or more groups) after comparing the groups' pre-period trends"
        ),
        limits=(
            "Impact only under the design's assumptions — no other change at the same time (ITS), parallel trends "
            "(DiD) — which the data can test only in part; no seasonal terms, covariates, staggered starts or "
            "synthetic controls; rows are averaged to one value per period (per group). Each failed or "
            "impossible check is reported as a caution with the result."
        ),
    ),
    Foundation(
        id="toc-process-tracing",
        applies_to=("theory_of_change",),
        method="Bayesian process tracing",
        citation=(
            "Van Evera (1997), *Guide to Methods for Students of Political Science* (hoop, smoking-gun, "
            "doubly-decisive and straw-in-the-wind tests); Bennett (2015), \"Disciplining Our Conjectures\", "
            "in Bennett & Checkel (eds), *Process Tracing*; Befani & Mayne (2014), \"Process Tracing and "
            "Contribution Analysis\", *IDS Bulletin* 45(6); Fairfield & Charman (2017), \"Explicit Bayesian "
            "Analysis for Process Tracing\", *Political Analysis* 25(3)"
        ),
        used_for=(
            "how far the evidence supports each link of a theory of change: a prior per link, each test's "
            "P(evidence | link holds) and P(evidence | it doesn't), odds-form updating for tests passed or "
            "failed, Van Evera's classification of each test, pathway confidence, and which test still to run "
            "would move a link most"
        ),
        limits=(
            "The probabilities are judgements, and the answer is only as good as them; tests on a link are "
            "treated as independent given whether it holds, and pathway confidence multiplies link posteriors "
            "as if the links were independent. It weighs evidence for a causal step; it doesn't estimate how "
            "large the effect is."
        ),
    ),
    Foundation(
        id="sd-simulation",
        applies_to=("sd",),
        method="Stock-and-flow simulation with dimensional analysis",
        citation=(
            "Forrester (1961), *Industrial Dynamics*; Sterman (2000), *Business Dynamics*, "
            "ch. 11 (delays)"
        ),
        used_for=(
            "unit-checked stock-flow integration (fixed-step Euler or adaptive RK23/RK45) "
            "with STEP, RAMP, PULSE and TABLE functions, SMOOTH/SMOOTH3 and DELAY1/DELAY3 "
            "delay structures, and provenance-carrying scenarios"
        ),
        limits=(
            "The adaptive RK option is RK45 under a step cap, not the classical "
            "fixed-step RK4 of Vensim/Stella."
        ),
    ),
    Foundation(
        id="sd-uncertainty",
        applies_to=("sd",),
        method="Uncertainty by Latin-hypercube sampling",
        citation="McKay, Beckman & Conover (1979), *Technometrics* 21(2)",
        used_for="seeded sampling of uncertain constants with percentile bands and Spearman rank correlations",
        limits="Capped at 1000 runs; rank correlations only, no variance decomposition.",
    ),
    Foundation(
        id="sd-sensitivity",
        applies_to=("sd",),
        method="One-at-a-time sensitivity",
        citation="Sterman (2000), *Business Dynamics*",
        used_for="tornado-style swings of each parameter's effect on a chosen metric, with a provenance overlay",
        limits="One-at-a-time only — no multi-way or derivative-based analysis.",
    ),
    Foundation(
        id="sd-loop-dominance",
        applies_to=("sd",),
        method="Loop dominance over a run (Loops That Matter)",
        citation=(
            "Schoenberg, Davidsen & Eberlein (2020), *System Dynamics Review*; "
            "revised score Schoenberg, Hayward & Eberlein (2023)"
        ),
        used_for=(
            "scoring every feedback loop at each step and flagging the loop (or fewest "
            "loops) holding half the score"
        ),
        limits=(
            "Enumerated exhaustively up to 500 loops — no strongest-path fallback; "
            "scores are zero whenever stocks stop changing, so the method explains "
            "change, not equilibrium."
        ),
    ),
    Foundation(
        id="bn-psa",
        applies_to=("bn",),
        method="Probabilistic sensitivity analysis by Monte Carlo",
        citation="sampling practice after McKay, Beckman & Conover (1979), *Technometrics* 21(2)",
        used_for=(
            "propagating uncertainty in CPT rows to the target's posterior — "
            "`bn set-uncertainty --n` marks uncertain rows, `bn monte-carlo` samples them"
        ),
        limits="Monte Carlo over declared uncertain rows only; EVPI deferred.",
    ),
    Foundation(
        id="evidence-source-check",
        applies_to=("*",),
        method="Source-vs-claim checking with a verification audit trail",
        citation=(
            "practice after Bradford Hill (1965) and GRADE (Guyatt et al. 2008); "
            "argumentation vocabulary from Toulmin (1958) — inspiration, not implemented criteria"
        ),
        used_for=(
            "recording whether a cited source supports the claim, who checked, which part "
            "of the source was read, and keeping sources for and against together on "
            "contested links"
        ),
        limits=(
            "Does not score claims against the Bradford Hill criteria and does not assign "
            "GRADE ratings; a check is only as good as the stored source text."
        ),
    ),
)

# Analysis result kinds (latris.operations.analysis_results.KIND_ORDER) mapped to
# the foundation entry they pull in. ``sd-simulation`` is a core entry: any
# genuine use of the SD formalism includes it, so it is deliberately absent here.
_ANALYSIS_KIND_TO_ID = {
    "sd-monte-carlo": "sd-uncertainty",
    "sd-options": "sd-uncertainty",
    "sd-sensitivity": "sd-sensitivity",
    "sd-loops": "sd-loop-dominance",
    "bn-monte-carlo": "bn-psa",
    "bn-options": "bn-psa",
    "dag-estimate": "dag-estimation",
    "fcm-inference": "fcm-steady-state",
    "toc-process-trace": "toc-process-tracing",
    "toc-impact": "toc-impact",
    "ft-monte-carlo": "risk-monte-carlo",
    "bt-monte-carlo": "risk-monte-carlo",
    "et-monte-carlo": "risk-monte-carlo",
    "dt-psa": "decision-psa",
    "markov-psa": "decision-psa",
    **{k: "global-sensitivity" for k in ("ft-gsa", "bt-gsa", "et-gsa", "dt-gsa", "markov-gsa", "sd-gsa")},
}


def foundation_for_result(result_kind: str, model_type: str) -> Foundation | None:
    """The method a result kind stands on: its own analysis entry where it has one, else its model type's
    core entry — what a surface shows beside the analysis (method, citation, limits)."""
    fid = _ANALYSIS_KIND_TO_ID.get(result_kind)
    if fid:
        return next(f for f in FOUNDATIONS if f.id == fid)
    analysis_ids = set(_ANALYSIS_KIND_TO_ID.values())
    return next((f for f in FOUNDATIONS if f.applies_to == (model_type,) and f.id not in analysis_ids), None)


class _EntriesFile(BaseModel):
    """The shape shared by every view attribute / role YAML file: ``entries:``."""

    entries: list = Field(default_factory=list)


def _has_view_attribute_content(paths: ProjectPaths, model_type: str) -> bool:
    """True if any view-attribute or role file for ``model_type`` holds entries.

    ``latris view set cld <edge> polarity +`` and ``latris sd set-role ...``
    are documented ways a project gains formalism content without ever
    touching the mapping registry, so they count as genuine use.
    """
    candidates = [
        *paths.parameters_dir.glob(f"{model_type}-*.yaml"),
        paths.roles_dir / f"{model_type}-roles.yaml",
    ]
    return any(f.is_file() and load_model(_EntriesFile, f).entries for f in candidates)


def _uses_formalism(paths: ProjectPaths, model_type: str) -> bool:
    """True if the project genuinely uses this formalism: any of

    - the type is selected in project.yaml (``latris project select-models``),
    - the mapping registry has members for it, or
    - it has stored view-attribute content (polarity, weights, roles, ...).
    """
    from latris.exporters._scope import view_member_ids

    foundation = load_model(ProjectFoundation, paths.project_yaml)
    if model_type in (foundation.selected_model_types or ()):
        return True
    if view_member_ids(paths, model_type) is not None:
        return True
    return _has_view_attribute_content(paths, model_type)


def _has_evidence_or_references(paths: ProjectPaths) -> bool:
    references = load_model(ReferenceLibrary, paths.references_yaml).entries
    evidence = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    return bool(references) or bool(evidence.entries)


def foundations_for_report(paths: ProjectPaths, *, model_type: str | None = None) -> list[Foundation]:
    """The entries relevant to one rendered report, in ``FOUNDATIONS`` order.

    Core model-type entries: when ``model_type`` is given (a scoped export),
    that type is included outright — the scoped export is itself the request
    for that formalism's report. In the aggregate report (``model_type=None``)
    a core entry is included when the project genuinely uses that formalism:
    it is selected in project.yaml, present in the mapping registry, or holds
    stored view-attribute content. Analysis entries are included only when
    the corresponding result kind is actually shown in the report's Results
    section: the same
    :func:`latris.operations.analysis_results.report_results` selection the
    exporter uses (latest run of each analysis, minus hidden ones, same
    ``model_types`` filter). The evidence entry is included when the project
    holds any references or evidence links.
    """
    from latris.operations.analysis_results import report_results

    results = report_results(model_types=[model_type] if model_type else None, root=paths.root)
    present_kinds = {res.run.result_kind for res in results}

    out: list[Foundation] = []
    seen: set[str] = set()
    for f in FOUNDATIONS:
        if f.applies_to == ("*",):
            include = _has_evidence_or_references(paths)
        elif f.id in _ANALYSIS_KIND_TO_ID.values():
            include = any(
                kind in present_kinds for kind, fid in _ANALYSIS_KIND_TO_ID.items() if fid == f.id
            )
        elif model_type is not None:
            include = f.applies_to == (model_type,)
        else:
            include = any(_uses_formalism(paths, mt) for mt in f.applies_to)
        if include and f.id not in seen:
            seen.add(f.id)
            out.append(f)
    return out


def render_methods_section(paths: ProjectPaths, *, model_type: str | None = None) -> list[str]:
    """Markdown lines for the report's Methods and foundations section.

    Empty list when nothing applies, so an early-stage project renders no
    section at all. No internal IDs — reader packs show this section.
    """
    entries = foundations_for_report(paths, model_type=model_type)
    if not entries:
        return []
    out = ["## Methods and foundations", ""]
    out.append(
        "_Established methods this model relies on, with their sources and stated limits. "
        "Latris cites a method only where it implements it — see the foundations reference "
        "for the full account._"
    )
    out.append("")
    for f in entries:
        limits = f" Limit: {f.limits}" if f.limits else ""
        out.append(f"- **{f.method}** — {f.used_for} ({f.citation}).{limits}")
    out.append("")
    return out
