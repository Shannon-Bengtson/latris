# Methods and foundations

Latris implements established methods and cites them. It does not invent a new
causal calculus, a new simulation algorithm, or a new theory of evidence — it
implements well-known ones, records which were used in each project, and states
their limits next to their results. This page is the map: for each formalism,
the literature it stands on, what Latris actually implements (with the command
or module that implements it), and what it deliberately does not do.

**The citation rule.** A work is cited only where Latris implements the method
it describes — not the whole book, and never a method that is only planned.
Where Latris borrows an idea as inspiration rather than implementation, the
text says so. If you find a citation here that overclaims, that is a bug:
please report it.

**One substrate, several formalisms.** Every model type in Latris shares the
same evidentiary substrate: links are claims, claims carry sources, sources
are checked against what they are claimed to support, and disagreement is
recorded rather than resolved silently. The formalisms below differ in what
kind of reasoning they support; the evidence discipline does not.

**Choosing between them.** The guide by question — "how does this work?"
(CLD), "can it be estimated?" (DAG), "how likely?" (BN), "which forces
dominate?" (FCM), "how does it behave over time?" (SD) — lives at
<https://latris.app/formalisms/>, mirrored for agents in the repo's
[`llms.txt`](../llms.txt) and the server help topic `model-types-overview`.

## Causal loop diagrams (qualitative)

- **Lineage.** Sterman (2000), *Business Dynamics*, ch. 4 — the canonical
  treatment of causal loop diagrams and loop polarity. Meadows (2008),
  *Thinking in Systems* — the accessible statement of the same tradition.
- **Implemented.** Loop detection by Johnson's (1975) elementary-circuits
  algorithm (`latris analyse loops`); polarity classification (an odd count of
  `−` edges makes a balancing loop); qualitative effect propagation along
  paths (`operations/graph_analysis.py`).
- **Limits.** A polarity of `~` (ambiguous) is reported as "unknown", not
  guessed. Loop enumeration is capped; beyond the cap Latris raises
  `TooManyLoops` rather than silently sampling. Decision-rule, governance and
  definitional edges are excluded from loop and centrality analysis — they
  are policy or identity links, not feedback mechanisms.

## Causal DAGs — identification, then estimation under stated assumptions

- **Lineage.** Pearl (2009), *Causality*; Pearl & Mackenzie (2018), *The Book
  of Why*; Hernán & Robins (2020), *Causal Inference: What If*. The
  d-separation test follows Shachter (1998), "Bayes-Ball".
- **Implemented.** d-separation queries, Markov blankets, path enumeration
  (with chain/fork/collider classification), and backdoor adjustment sets by
  graph surgery — the exposure's outgoing edges removed, then testing which
  sets d-separate exposure from outcome (`latris analyse`, DAG-scoped).
- **Effect estimation** (`latris analyse estimate`). With a dataset, the
  average effect of one factor on another by back-door adjustment (Pearl
  2009): the smallest valid back-door set made only of measured factors (or
  a set you give, checked against the DAG), then outcome regression
  (Hernán & Robins 2020, ch. 15) — ordinary least squares with HC3 robust
  standard errors (MacKinnon & White 1985) for a numeric outcome, logistic
  regression (odds ratio and average marginal effect) for a two-valued one,
  via statsmodels (Seabold & Perktold 2010). The unadjusted association is
  reported beside it. If every valid set needs a factor the dataset doesn't
  measure, Latris names what to measure and estimates nothing.
- **Limits — read this before citing Pearl.** An estimate is causal only if
  the DAG leaves out no common cause of treatment and outcome, the model's
  form is right (linear or logistic, additive in the adjustment variables,
  no effect modification), and positivity holds; the report states these
  every time. Complete cases only. One numeric or two-valued treatment at a
  time. No g-computation, inverse-probability weighting, instrumental
  variables or front-door estimation, and no counterfactual computation
  anywhere in the package. Minimal adjustment sets are enumerated up to size
  3; the search for a measured set goes to size 6. Analyses run on the
  causal-edge subgraph only.

## Bayesian networks

- **Lineage.** Pearl (1988), *Probabilistic Reasoning in Intelligent Systems*
  — the founding text. Fenton & Neil (2018), *Risk Assessment and Decision
  Analysis with Bayesian Networks* (2nd ed.) — the closest in spirit to
  Latris: expert-elicited structure, defensible numbers, argued cases. Soft
  (likelihood) evidence follows Jeffrey (1965), *The Logic of Decision*.
- **Implemented.** Exact inference by variable elimination (pgmpy), per-node
  posterior marginals; soft (likelihood) evidence per node — weights need not
  sum to one (`--likelihood`); `bn explain` for the most probable joint
  states (MAP, or MPE when all variables are queried) with margins; Noisy-OR
  canonical models (binary nodes); CPT parameter
  learning from data (MLE / Bayesian-Dirichlet estimators) with
  human-elicited rows protected from overwrite and learned rows marked
  `data-derived`; one-way (tornado) sensitivity of a target node over CPT
  cells, with a provenance overlay; probabilistic sensitivity analysis by
  Monte Carlo over uncertain CPT rows (`bn set-uncertainty --n` with
  `bn monte-carlo`) (`latris bn …`).
- **Limits.** Variable elimination only — no junction tree or belief
  propagation. Marginals, not joints. Noisy-OR requires binary nodes and
  parents. Tornado sensitivity is one-way; probabilistic sensitivity analysis
  ships separately by Monte Carlo, as above; EVPI is deferred. Structure
  learning is excluded by design — see `latris capabilities`,
  `excluded_by_design`.

## Fuzzy cognitive maps

- **Lineage.** Kosko (1986), "Fuzzy Cognitive Maps", *International Journal
  of Man-Machine Studies* 24(1) — weighted matrix iteration to a steady state.
- **Implemented.** `A ← f(A·W)` iterated to convergence with sigmoid (default),
  tanh-rescaled, or step transfer functions; clamped scenario nodes; weights
  validated to [−1, +1] (`latris fcm …`).
- **Limits.** Fixed-point analysis only. A run that does not converge is
  flagged `converged=False`; limit cycles are not detected or classified.

## System dynamics

- **Lineage.** Forrester (1961), *Industrial Dynamics*; Sterman (2000),
  *Business Dynamics*; Meadows (2008). Loop dominance follows the Loops That
  Matter method — Schoenberg, Davidsen & Eberlein (2020), *System Dynamics
  Review* — with the revised flow-to-stock link score of Schoenberg, Hayward &
  Eberlein (2023), the approach Stella and pysimlin ship.
- **Implemented.** Stock-and-flow simulation with dimensional analysis (pint;
  custom base dimensions for person, dollar, item): fixed-step forward Euler,
  or adaptive RK23/RK45; STEP, RAMP, PULSE, TABLE and arithmetic builtins;
  SMOOTH/SMOOTH3 information smoothing and DELAY1/DELAY3 material delays,
  expanded into stock-and-flow structure (Sterman 2000, ch. 11);
  unit-checked scenario overrides with provenance (`latris sd …`); uncertainty
  by seeded Latin-hypercube sampling (McKay, Beckman & Conover 1979) with
  percentile bands and Spearman rank correlations; one-at-a-time sensitivity;
  per-step loop dominance scores with dominant loops flagged
  (`latris sd loops`).
- **Limits.** The adaptive RK option is `solve_ivp` RK45 with a step cap — not
  the classical fixed-step RK4 of Vensim/Stella. Loop dominance enumerates
  loops exhaustively (Johnson's algorithm) up to a cap of 500; larger models
  would need the strongest-path search, which is not implemented. Scores are
  zero whenever stocks stop changing — the method explains change, not
  equilibrium. Monte Carlo is capped at 1000 runs and reports rank
  correlations only.

## Fault trees

- **Lineage.** Vesely, Goldberg, Roberts & Haasl (1981), *Fault Tree
  Handbook* (NUREG-0492, US Nuclear Regulatory Commission), and IEC
  61025:2006. Minimal cut sets by MOCUS-style expansion (Fussell & Vesely
  1972); the exact top-event probability from a binary decision diagram
  (Rauzy 1993); importance after Birnbaum (1969) and Fussell (1975).
- **Implemented.** Event types as view roles (top, intermediate, basic,
  undeveloped); AND, OR and k-out-of-n (vote) gates stored on their events.
  Minimal cut sets with superset elimination at every gate, so an event that
  feeds several gates is handled correctly; single points of failure (cut
  sets of one). When every leaf has a probability: the exact top-event
  probability from a reduced ordered BDD, with the rare-event approximation
  and the min-cut upper bound beside it; Birnbaum importance
  (P(top | e) − P(top | not e)), Fussell–Vesely importance
  ((P(top) − P(top | not e)) / P(top)) and risk achievement worth
  (P(top | e) / P(top)), each computed exactly on the diagram. Every
  probability keeps its origin, source and verification, and important
  values nobody has verified are flagged (`latris ft …`).
- **Limits.** Static, coherent trees only: no NOT, priority-AND, sequence or
  other dynamic gates. Basic events are assumed independent — there is no
  common-cause failure model (beta factor, MGL), so redundancy can look
  stronger than it is. Uncertainty is propagated by Monte Carlo (below),
  but there is no conversion from failure rates and exposure times
  (enter the probability for the period the tree is about). Cut sets are
  listed up to 20,000; past that, limit the order.

## Bow-ties

- **Lineage.** CCPS & Energy Institute (2018), *Bow Ties in Risk
  Management: A Concept Book for Process Safety* — the elements, the barrier
  types and the rules for drawing lines; the quantification is layer of
  protection analysis, CCPS (2001).
- **Implemented.** Hazard, top event, threats, consequences, barriers and
  escalation factors as view roles; lines as ordinary links, checked against
  the bow-tie pattern. Per barrier: CCPS type, status (in place, degraded,
  not in place), owner and probability of failure on demand, with
  provenance. The analysis lists every line with its effective barriers
  (degraded or missing ones don't count) and flags lines with none or one,
  barriers on more than one line, escalation factors with no control and
  barriers with no owner. With every threat's frequency and every barrier's
  PFD: the top-event frequency (Σ over threats of frequency × probability
  that some route gets through), each consequence's frequency, and risk
  achievement worth per barrier. A threat's routes are combined exactly with
  the fault-tree decision diagram, so a barrier on two routes counts once.
- **Limits.** Barriers are assumed to fail independently — shared barriers
  are flagged, but common-cause failure isn't modelled; LOPA is an
  order-of-magnitude method; its values are points unless given ranges for
  Monte Carlo (below). Escalation factors
  are drawn and checked but not quantified, and there is no consequence
  severity or risk matrix.

## Event trees

- **Lineage.** IEC 62502:2010, *Event tree analysis*; the US NRC *PRA
  Procedures Guide* (NUREG/CR-2300, 1983), descending from the *Reactor
  Safety Study* (WASH-1400, 1975).
- **Implemented.** Initiating event, headings (functional events) and end
  states as view roles; the heading order and the sequences stored as data.
  A check that the sequences form a complete tree: at every branch point all
  sequences ask the same next heading, both answers are covered, and none
  stops while a sibling continues. P(yes) per heading, in general or given
  earlier answers (the most specific match applies; two equally specific
  values that disagree are reported, not guessed). Each sequence's
  probability is the product of its branch probabilities; with the
  initiating frequency, its frequency per year; totals per end state with
  the dominant sequence behind each. Every value keeps its provenance.
- **Limits.** Binary branches only; dependence between headings exists only
  as the conditional probabilities you state; uncertainty only by Monte
  Carlo over stated ranges (below); heading probabilities are entered (they can cite a fault-tree
  run) rather than computed from linked fault trees.

## Uncertainty in the risk models (Monte Carlo)

- **Lineage.** Probabilistic risk assessment propagates parameter
  uncertainty by sampling (NUREG/CR-2300, ch. 12), with each input's
  state-of-knowledge distribution usually a lognormal stated by its median
  and *error factor* (95th percentile over the median); the epistemic
  reading of those distributions is Apostolakis (1990). Latin hypercube
  sampling follows McKay, Beckman & Conover (1979) and Helton & Davis
  (2003).
- **Implemented.** `latris ft|bowtie|et uncertainty` gives a basic event's
  probability, a barrier's PFD, a threat's or initiator's frequency, or a
  heading's (conditional) P(yes) a distribution — lognormal by median and
  error factor, or uniform, triangular, normal, beta, gamma — kept within
  [0, 1] for probabilities, with provenance and a reason; the range must
  include the current value. `monte-carlo` samples them (seeded Latin
  hypercube by default) through the type's own calculation — the fault
  tree's exact decision diagram, the bow-tie's line combination, the event
  tree's sequence products — and reports each result's 5th, 50th and 95th
  percentiles and mean beside the point estimate, and Spearman rank
  correlations for what drives the spread. Each input takes one value per
  run wherever it appears, so a barrier on two lines or an event under two
  gates is not treated as two independent copies.
- **Limits.** Different inputs are sampled independently: no correlation
  between, say, two pumps' failure probabilities beyond what a shared event
  expresses. Inputs without a range are held exact, so the spread is a lower
  bound. Rank correlation captures monotone influence only; global
  sensitivity indices are not computed.

## Multi-criteria decision analysis

- **Lineage.** The additive value model of multi-attribute value theory
  (Keeney & Raiffa 1976), as set out for practice by Belton & Stewart
  (2002) and for public-sector appraisal in the UK government's
  *Multi-criteria analysis: a manual* (DCLG 2009). Weights are swing
  weights: how much moving from the worst to the best of each criterion's
  scale matters, relative to the other criteria's swings.
- **Implemented.** Options and criteria as view roles. Each score becomes a
  value from 0 to 1 on a linear scale between the criterion's worst and best
  (stated, or the options' range, flagged); values are combined by
  normalised weights into a total out of 100. The analysis gives the
  ranking with each criterion's contribution, dominated options, and for
  each weight the nearest values — the others keeping their proportions —
  at which the top choice changes (exact, since totals are linear in one
  weight). It names the scores the winning margin rests on that nobody has
  verified. Every weight and score keeps its provenance.
- **Limits.** Assumes preferential independence and linear value between
  worst and best; scores outside a stated scale are clipped (and flagged).
  Weights mean nothing apart from their scales, and scales taken from the
  options' range shift when an option is added. One-way weight sensitivity
  only; no probabilistic weights or scores; no AHP, outranking (ELECTRE,
  PROMETHEE) or TOPSIS.

## Analysis of competing hypotheses

- **Lineage.** Heuer (1999), *Psychology of Intelligence Analysis*, ch. 8;
  Heuer & Pherson (2015), *Structured Analytic Techniques for Intelligence
  Analysis*. The method's core: judge hypotheses by the evidence *against*
  them, because evidence consistent with every hypothesis proves nothing.
- **Implemented.** Hypotheses and evidence items as view roles; every item
  rated against every hypothesis (CC very consistent, C, N neutral or not
  applicable, I, II very inconsistent) with its reasoning and provenance;
  each item's credibility and relevance. Hypotheses ranked by weighted
  inconsistency; items rated identically against every hypothesis flagged as
  non-diagnostic; linchpins — items without which the lead changes or ties —
  found by leaving each out in turn, with whether their own sources (the
  item's citations) were checked.
- **Limits.** Ratings and weights are judgements. The weights — high 1.0,
  medium 0.7, low 0.4 (credibility × relevance), an inconsistency 1 and a
  strong one 2 — are Latris's stated convention, not Heuer's. Items are
  treated as independent, and no probabilities are computed: the ranking
  orders hypotheses, it doesn't say how likely each is.

## Decision trees and the value of information

- **Lineage.** Raiffa (1968), *Decision Analysis*; Clemen & Reilly (2014),
  *Making Hard Decisions*; the value of information after Howard (1966).
- **Implemented.** Decision, chance and terminal nodes as view roles;
  branches as links, each with a label, a probability (from chance nodes)
  and an optional value along it; payoffs at terminals; maximise or
  minimise. Rollback by expected value to the optimal strategy and each
  first choice's value. The expected value of perfect information for each
  uncertainty — chance nodes that resolve the same uncertainty under
  different choices are grouped by name and must agree on its states and
  probabilities — and for all of them together (treated as independent).
  For each two-state uncertainty, the probabilities at which the best first
  choice changes, found by scanning and bisection. Every value keeps its
  provenance; unverified values on the best path are named.
- **Limits.** Risk-neutral (no utility function). Probabilities and payoffs
  are point values unless given a range for the probabilistic sensitivity
  analysis (below). EVPI is undefined for
  an uncertainty whose probabilities depend on the choice (it is reported
  as not priced), and is an upper bound — imperfect information (EVSI) is
  not computed. A node has one parent; shared subtrees are repeated.

## Markov cohort models and cost-effectiveness

- **Lineage.** Sonnenberg & Beck (1993), "Markov Models in Medical Decision
  Making"; Briggs, Claxton & Sculpher (2006), *Decision Modelling for Health
  Economic Evaluation*; incremental analysis after Drummond et al. (2015).
- **Implemented.** States and strategies as view roles; per-cycle transition
  probabilities on links (for every strategy, or overridden for one), the
  rest staying; per-state cost per cycle and utility per year (likewise);
  the starting cohort. The cohort trace; discounted costs and outcomes
  (separate rates allowed) with optional half-cycle correction — the
  trapezoid rule, discounting at mid-cycle; expected time in each state.
  Incremental analysis: dominated and extendedly dominated strategies,
  ICERs along the frontier, and net monetary benefit at a willingness to
  pay. Every value keeps its provenance.
- **Limits.** Memoryless — the chance of moving depends only on the current
  state (no tunnel states or time-varying probabilities yet). Values are
  point estimates unless given a range for the probabilistic sensitivity
  analysis (below). A cohort expectation, not individual simulation; MDPs
  (choosing actions in each state) are not implemented.

## Probabilistic sensitivity analysis (decision trees and Markov models)

- **Lineage.** Briggs, Claxton & Sculpher (2006), *Decision Modelling for
  Health Economic Evaluation*, ch. 4–7; acceptability curves after Fenwick,
  Claxton & Sculpher (2001); the expected value of perfect information over
  the parameters after Claxton (1999); Latin hypercube sampling after
  McKay, Beckman & Conover (1979).
- **Implemented.** Ranges on a decision tree's payoffs, branch values and
  probabilities (one branch of a two-branch chance node, or every branch as
  a Dirichlet worth n observations; chance nodes resolving the same
  uncertainty take the same sampled probabilities), and on a Markov model's
  transition probabilities, costs and utilities (each for every strategy or
  one; a state's transitions out as a Dirichlet). Beta and gamma by mean
  and standard deviation (method of moments), or any of uniform,
  triangular, normal and lognormal; each range keeps its reason, source and
  verification and must include the current value. Seeded Latin hypercube
  sampling through each model's own calculation. Decision trees: each first
  choice's expected value across the runs, how often each is best, and the
  EVPI over the parameters. Markov: each strategy's cost and outcome across
  the runs, the incremental analysis on the means, the cost-effectiveness
  acceptability curve and EVPI over a willingness-to-pay grid, and the
  probability the chosen strategy is cost-effective at the stated
  willingness to pay. Spearman rank correlation names the inputs driving
  the decision (the best option's advantage, or its net monetary benefit,
  over the runner-up).
- **Limits.** Inputs are sampled independently (no correlated draws). EVPI
  is for all parameters together; partial EVPI (EVPPI) and sample
  information (EVSI) are not computed. Separately sampled probabilities of
  leaving a Markov state that sum past 1 are scaled down to 1, and the
  report counts how often; a Dirichlet over the state avoids it.

## Global sensitivity analysis (Sobol indices, Morris screening)

- **Lineage.** Saltelli et al. (2008), *Global Sensitivity Analysis: The
  Primer*; variance-based indices after Sobol (2001), estimated as in
  Saltelli et al. (2010) (first order) and Jansen (1999) (total); elementary
  effects after Morris (1991), with μ* after Campolongo, Cariboni & Saltelli
  (2007).
- **Implemented.** For fault trees, bow-ties, event trees, decision trees,
  Markov models, system dynamics and Bayesian networks, every input with a range (the same
  distributions their Monte Carlo or PSA samples) is varied together on the
  unit hypercube and mapped through its quantile function. Sobol: a
  scrambled Sobol sequence, n·(k + 2) runs, first-order and total indices
  for every output with bootstrap 95% intervals. Morris: r trajectories on a
  four-level grid over each input's central 95%, r·(k + 1) runs, μ*, μ and σ
  with a bootstrap interval on μ*. The headline output is the model's main
  result (the top event, the best option's advantage over the runner-up,
  the net monetary benefit at the willingness to pay, an SD variable's
  metric, a Bayesian network's posterior). A set of probabilities — a
  chance node's branches, a state's transitions out, a Bayesian-network
  table worth n observations — is one input spanning several columns,
  decoded into an exact Dirichlet draw (each component a gamma quantile,
  normalised) and indexed as a group (Jacques, Lavergne & Devictor 2006).
  Implemented on numpy and scipy rather than SALib; checked
  against the Ishigami function's analytic indices and closed forms.
- **Limits.** Inputs must be independent (correlations between ranges are
  ignored by this analysis); a group's index covers the whole set, not each
  of its rows. Index
  estimates carry sampling error — with heavy-tailed inputs or small n they
  can stray outside [0, 1]; the intervals say how far to trust them. Morris
  effects are per unit of an input's quantile and comparable only within
  one result.

## Theory of change

- **Lineage.** Weiss (1995), "Nothing as Practical as Good Theory" — a theory
  of change states how an intervention is expected to work, step by step,
  with its assumptions made explicit; the logic-model levels follow the W.K.
  Kellogg Foundation (2004), *Logic Model Development Guide*; reading the
  chain link by link against the evidence follows contribution analysis
  (Mayne 2012, *Evaluation* 18(3)).
- **Implemented.** Six levels as view roles — input, activity, output,
  short-term outcome, long-term outcome, impact (the outcome of interest).
  Readiness requires a level on every factor, no link back to an earlier
  level, an activity and an impact, every impact reached from an activity and
  no dead ends. `latris toc check` enumerates every simple pathway from an
  activity to an impact (up to 200) and gives each link an evidence status —
  *checked* (a source read and found to support it), *cited* (a source not yet
  checked), *untested* (none) or *contested* (a source against it) — with its
  count of stated assumptions; a pathway takes its weakest link's status.
  Links that skip two or more levels are flagged as leaps. The result is
  recorded and goes out of date when sources, checks or assumptions change.
- **Process tracing.** Bayesian process tracing (Bennett 2015; Befani &
  Mayne 2014; Fairfield & Charman 2017) weighs how far the evidence supports
  each link. A link has a prior (default 0.5) and evidence *tests*, each with
  P(E | link holds) — its certainty — and P(E | it doesn't), whose complement
  is its uniqueness. `latris toc trace` multiplies the link's odds by
  P(E|H)/P(E|¬H) for each test passed and (1−P(E|H))/(1−P(E|¬H)) for each
  failed, classifies each test by Van Evera's (1997) four types (hoop: certain,
  P(E|H) ≥ 0.8; smoking gun: unique, P(E|¬H) ≤ 0.2; doubly decisive: both;
  straw in the wind: neither), gives each pathway the product of its links'
  posteriors, and ranks tests still to run by how far they could move their
  link. Probabilities are kept open (strictly between 0 and 1), so no single
  test settles a link outright.
- **Impact.** `latris toc impact` estimates the change in an outcome from a
  registered dataset. Without a comparison group it is an interrupted time
  series: segmented regression (Wagner et al. 2002; Bernal, Cummins &
  Gasparrini 2017) with a step and change of slope at the start, AR(1) errors
  by iterated GLS (Prais & Winsten 1954) — in simulation, Newey–West errors
  covered well under 95% on series this short — and the effect by the last period
  against the projected pre-period trend. With one it is
  difference-in-differences (Angrist & Pischke 2009): the interaction of group
  and period, cluster-robust by group when there are 20 or more groups
  (Bertrand, Duflo & Mullainathan 2004), after a test of whether the groups'
  pre-period trends differ. Each check that fails or can't be made — fewer
  than 8 periods a side, strong autocorrelation in a short series, diverging pre-trends, too few groups
  to cluster, uneven spacing — is reported as a caution.
- **Limits.** The check and process tracing are structural and evidential:
  they show where a results chain rests on untested or contested steps, not
  how large an effect is. The impact estimate attributes a change to the
  intervention only under its design's assumptions (no other change at the
  same time; parallel trends), which the data test only in part; it has no
  seasonal terms, covariates, staggered starts or synthetic controls.
  Process tracing is only as good as its probability judgements; it treats
  tests on a link as independent given the link, and links on a pathway as
  independent of each other. Feedback within a programme (a ToC is kept
  acyclic) belongs in a CLD on the same substrate.

## The evidence discipline

- **Lineage.** The substrate's vocabulary — claims, warrants, rebuttals — is
  Toulmin's (1958), *The Uses of Argument*. The wider tradition of marshalling
  evidence for and against a claim includes Wigmore (1937) and Schum (1994).
  The practice of recording *which part of a source was read* and *whether it
  supports the claim* follows the evidence-assessment tradition of Bradford
  Hill (1965) and the grading of evidence quality in GRADE (Guyatt et al.
  2008). These are inspirations for the audit trail, not implemented
  criteria: Latris does not score a link against the Bradford Hill checklist,
  and it does not assign GRADE ratings.
- **Implemented.** Source-vs-claim checks with verdicts
  (`latris evidence check`: supports / contradicts / orthogonal /
  insufficient extract); an AI's check must quote the source and the quote is
  looked up in the text Latris holds (`latris ref snapshot`) — a paraphrase
  is refused; every check records who made it and the source's access tier
  (title, abstract, extract, full text). Contested links keep sources for and
  against on the same link and report both. Challenges are an adversarial
  review log with a conversation and a terminal state.
- **Limits.** A Toulmin/IBIS argument-map model type is registered
  (`latris capabilities` lists it) but not planned; the substrate borrows the
  vocabulary, it does not implement the formalism. Checks are only as good as
  the stored source text — a check against an abstract cannot speak for the
  full text.

## Where each formalism sits on the ladder of causation

Pearl & Mackenzie (2018) order causal questions as association → intervention
→ counterfactual. Honest placement:

| Formalism | Position |
|---|---|
| CLD | Mechanism claims — qualitative structure only; arrows are argued, not estimated |
| FCM | Semi-quantitative simulation of the claimed mechanism |
| SD | Quantitative mechanism simulation; scenario analysis intervenes *on the model* |
| Theory of Change | Mechanism claims laid out as a results chain, each step read against its evidence — with process tracing, weighed by Bayes' rule; with data, an interrupted-time-series or difference-in-differences impact estimate, valid only under that design's assumptions |
| Fault Tree | Logical decomposition of how a failure can occur; probabilities assume independent basic events, optionally with Monte Carlo over their uncertainty — no causal estimation |
| Bow-Tie | Barrier structure around one event; LOPA frequencies are order-of-magnitude, barriers assumed independent |
| Event Tree | Forward sequences from one event; probabilities are as conditional as you state them — no causal estimation |
| MCDA | Not causal: a structured comparison of options under stated weights |
| ACH | Weighs explanations against evidence; orders hypotheses, gives no probabilities |
| Decision tree | Choices under stated probabilities; the value of knowing them first — not causal estimation |
| Markov model | Expected costs and outcomes under stated transition probabilities — not causal estimation |
| DAG / BN | Observational queries and identification — what to measure; with data, an average effect by back-door adjusted regression, valid only under the DAG's assumptions; no counterfactuals |

A CLD arrow is not a structural equation and carries no do-semantics; a
successful scenario run says what the model does under an assumed change, not
what the world would do. Reports should be quoted with that in mind — and
Latris reports say it themselves in the Methods section.

## Deliberately not implemented

Black-box machine learning and opaque structure learning (they fail the
inspectability test — `latris capabilities`, `excluded_by_design`);
counterfactual estimation, and interventional estimation beyond back-door
adjusted regression on a DAG and the two quasi-experimental impact designs on
a theory of change (interrupted time series, difference-in-differences);
XMILE/Vensim import
(off the roadmap). See the capability manifest for the living list.

## Machine-readable source of truth

The report's **Methods and foundations** section and the capability manifest's
`foundations` block are generated from the same registry,
`latris.operations.foundations` (`latris foundations --json` for the raw
list). This page is the prose companion; if the two disagree, the registry and
the code it describes win, and this page is wrong.

## References

- Angrist, J. D., & Pischke, J.-S. (2009). *Mostly Harmless Econometrics:
  An Empiricist's Companion*. Princeton University Press.
- Apostolakis, G. (1990). "The Concept of Probability in Safety Assessments
  of Technological Systems." *Science*, 250(4986), 1359–1364.
- Befani, B., & Mayne, J. (2014). "Process Tracing and Contribution
  Analysis: A Combined Approach to Generative Causal Inference for Impact
  Evaluation." *IDS Bulletin*, 45(6), 17–36.
- Belton, V., & Stewart, T. J. (2002). *Multiple Criteria Decision Analysis:
  An Integrated Approach*. Kluwer.
- Bennett, A. (2015). "Disciplining Our Conjectures: Systematizing Process
  Tracing with Bayesian Analysis." In A. Bennett & J. T. Checkel (Eds.),
  *Process Tracing: From Metaphor to Analytic Tool*. Cambridge University
  Press.
- Bernal, J. L., Cummins, S., & Gasparrini, A. (2017). "Interrupted time
  series regression for the evaluation of public health interventions: a
  tutorial." *International Journal of Epidemiology*, 46(1), 348–355.
- Bertrand, M., Duflo, E., & Mullainathan, S. (2004). "How Much Should We
  Trust Differences-in-Differences Estimates?" *Quarterly Journal of
  Economics*, 119(1), 249–275.
- Birnbaum, Z. W. (1969). "On the Importance of Different Components in a
  Multicomponent System." In P. R. Krishnaiah (Ed.), *Multivariate Analysis
  II*. Academic Press.
- Bradford Hill, A. (1965). "The Environment and Disease: Association or
  Causation?" *Proceedings of the Royal Society of Medicine*, 58(5), 295–300.
- Briggs, A., Claxton, K., & Sculpher, M. (2006). *Decision Modelling for
  Health Economic Evaluation*. Oxford University Press.
- Campolongo, F., Cariboni, J., & Saltelli, A. (2007). "An effective screening
  design for sensitivity analysis of large models." *Environmental Modelling
  & Software*, 22(10), 1509–1518.
- CCPS & Energy Institute (2018). *Bow Ties in Risk Management: A Concept
  Book for Process Safety*. AIChE / Wiley.
- CCPS — Center for Chemical Process Safety (2001). *Layer of Protection
  Analysis: Simplified Process Risk Assessment*. AIChE.
- Claxton, K. (1999). "The irrelevance of inference: a decision-making
  approach to the stochastic evaluation of health care technologies."
  *Journal of Health Economics*, 18(3), 341–364.
- Clemen, R. T., & Reilly, T. (2014). *Making Hard Decisions with
  DecisionTools* (3rd ed.). Cengage.
- Department for Communities and Local Government (2009). *Multi-criteria
  analysis: a manual*. London: DCLG.
- Drummond, M. F., Sculpher, M. J., Claxton, K., Stoddart, G. L., &
  Torrance, G. W. (2015). *Methods for the Economic Evaluation of Health
  Care Programmes* (4th ed.). Oxford University Press.
- Fairfield, T., & Charman, A. E. (2017). "Explicit Bayesian Analysis for
  Process Tracing: Guidelines, Opportunities, and Caveats." *Political
  Analysis*, 25(3), 363–380.
- Fenton, N., & Neil, M. (2018). *Risk Assessment and Decision Analysis with
  Bayesian Networks* (2nd ed.). CRC Press.
- Fenwick, E., Claxton, K., & Sculpher, M. (2001). "Representing
  uncertainty: the role of cost-effectiveness acceptability curves."
  *Health Economics*, 10(8), 779–787.
- Forrester, J. W. (1961). *Industrial Dynamics*. MIT Press.
- Fussell, J. B. (1975). "How to Hand-Calculate System Reliability and
  Safety Characteristics." *IEEE Transactions on Reliability*, R-24(3),
  169–174.
- Fussell, J. B., & Vesely, W. E. (1972). "A New Methodology for Obtaining
  Cut Sets for Fault Trees." *Transactions of the American Nuclear
  Society*, 15, 262–263.
- Guyatt, G., et al. (2008). "GRADE: an emerging consensus on rating quality
  of evidence and strength of recommendations." *BMJ*, 336, 924–926.
- Helton, J. C., & Davis, F. J. (2003). "Latin hypercube sampling and the
  propagation of uncertainty in analyses of complex systems." *Reliability
  Engineering & System Safety*, 81(1), 23–69.
- Hernán, M., & Robins, J. (2020). *Causal Inference: What If*. Chapman &
  Hall/CRC. <https://hsph.harvard.edu/causalinference/>
- Heuer, R. J. (1999). *Psychology of Intelligence Analysis*. Center for the
  Study of Intelligence, Central Intelligence Agency.
- Heuer, R. J., & Pherson, R. H. (2015). *Structured Analytic Techniques for
  Intelligence Analysis* (2nd ed.). CQ Press.
- Howard, R. A. (1966). "Information Value Theory." *IEEE Transactions on
  Systems Science and Cybernetics*, 2(1), 22–26.
- IEC 61025:2006. *Fault tree analysis (FTA)*. International
  Electrotechnical Commission.
- IEC 62502:2010. *Analysis techniques for dependability — Event tree
  analysis (ETA)*. International Electrotechnical Commission.
- Jacques, J., Lavergne, C., & Devictor, N. (2006). "Sensitivity analysis
  in presence of model uncertainty and correlated inputs." *Reliability
  Engineering & System Safety*, 91(10–11), 1126–1134.
- Jansen, M. J. W. (1999). "Analysis of variance designs for model output."
  *Computer Physics Communications*, 117(1–2), 35–43.
- Jeffrey, R. (1965). *The Logic of Decision*. McGraw-Hill.
- Johnson, D. B. (1975). "Finding all the elementary circuits of a directed
  graph." *SIAM Journal on Computing*, 4(1), 77–84.
- Keeney, R. L., & Raiffa, H. (1976). *Decisions with Multiple Objectives:
  Preferences and Value Tradeoffs*. Wiley.
- Kellogg Foundation, W.K. (2004). *Logic Model Development Guide*. W.K.
  Kellogg Foundation.
- Kosko, B. (1986). "Fuzzy Cognitive Maps." *International Journal of
  Man-Machine Studies*, 24(1), 65–75.
- MacKinnon, J. G., & White, H. (1985). "Some heteroskedasticity-consistent
  covariance matrix estimators with improved finite sample properties."
  *Journal of Econometrics*, 29(3), 305–325.
- Mayne, J. (2012). "Contribution analysis: Coming of age?" *Evaluation*,
  18(3), 270–280.
- McKay, M. D., Beckman, R. J., & Conover, W. J. (1979). "A Comparison of
  Three Methods for Selecting Values of Input Variables in the Analysis of
  Output from a Computer Code." *Technometrics*, 21(2), 239–245.
- Meadows, D. H. (2008). *Thinking in Systems: A Primer*. Chelsea Green.
- Morris, M. D. (1991). "Factorial sampling plans for preliminary
  computational experiments." *Technometrics*, 33(2), 161–174.
- Pearl, J. (1988). *Probabilistic Reasoning in Intelligent Systems: Networks
  of Plausible Inference*. Morgan Kaufmann.
- Pearl, J. (2009). *Causality: Models, Reasoning and Inference* (2nd ed.).
  Cambridge University Press.
- Pearl, J., & Mackenzie, D. (2018). *The Book of Why: The New Science of
  Cause and Effect*. Basic Books.
- Prais, S. J., & Winsten, C. B. (1954). *Trend Estimators and Serial
  Correlation*. Cowles Commission Discussion Paper No. 383.
- Raiffa, H. (1968). *Decision Analysis: Introductory Lectures on Choices
  under Uncertainty*. Addison-Wesley.
- Rauzy, A. (1993). "New Algorithms for Fault Trees Analysis."
  *Reliability Engineering & System Safety*, 40(3), 203–211.
- Saltelli, A., Annoni, P., Azzini, I., Campolongo, F., Ratto, M., &
  Tarantola, S. (2010). "Variance based sensitivity analysis of model
  output." *Computer Physics Communications*, 181(2), 259–270.
- Saltelli, A., Ratto, M., Andres, T., Campolongo, F., Cariboni, J.,
  Gatelli, D., Saisana, M., & Tarantola, S. (2008). *Global Sensitivity
  Analysis: The Primer*. Wiley.
- Schoenberg, S., Davidsen, P., & Eberlein, R. (2020). "Loops That Matter."
  *System Dynamics Review*.
- Schoenberg, S., Hayward, J., & Eberlein, R. (2023). Revised flow-to-stock
  link score for Loops That Matter. *System Dynamics Review*.
- Schum, D. A. (1994). *Evidential Foundations of Probabilistic Reasoning*.
  Wiley.
- Seabold, S., & Perktold, J. (2010). "statsmodels: Econometric and
  Statistical Modeling with Python." *Proceedings of the 9th Python in
  Science Conference*.
- Shachter, R. D. (1998). "Bayes-Ball: The Rational Pastime." *Proceedings of
  the 14th Conference on Uncertainty in Artificial Intelligence (UAI)*.
- Sobol, I. M. (2001). "Global sensitivity indices for nonlinear
  mathematical models and their Monte Carlo estimates." *Mathematics and
  Computers in Simulation*, 55(1–3), 271–280.
- Sonnenberg, F. A., & Beck, J. R. (1993). "Markov Models in Medical
  Decision Making: A Practical Guide." *Medical Decision Making*, 13(4),
  322–338.
- Sterman, J. D. (2000). *Business Dynamics: Systems Thinking and Modeling
  for a Complex World*. Irwin/McGraw-Hill.
- Toulmin, S. E. (1958). *The Uses of Argument*. Cambridge University Press.
- US Nuclear Regulatory Commission (1975). *Reactor Safety Study*
  (WASH-1400, NUREG-75/014).
- US Nuclear Regulatory Commission (1983). *PRA Procedures Guide*
  (NUREG/CR-2300).
- Van Evera, S. (1997). *Guide to Methods for Students of Political
  Science*. Cornell University Press.
- Vesely, W. E., Goldberg, F. F., Roberts, N. H., & Haasl, D. F. (1981).
  *Fault Tree Handbook* (NUREG-0492). U.S. Nuclear Regulatory Commission.
- Wagner, A. K., Soumerai, S. B., Zhang, F., & Ross-Degnan, D. (2002).
  "Segmented regression analysis of interrupted time series studies in
  medication use research." *Journal of Clinical Pharmacy and Therapeutics*,
  27(4), 299–309.
- Weiss, C. H. (1995). "Nothing as Practical as Good Theory: Exploring
  Theory-Based Evaluation for Comprehensive Community Initiatives for
  Children and Families." In J. P. Connell, A. C. Kubisch, L. B. Schorr & C.
  H. Weiss (Eds.), *New Approaches to Evaluating Community Initiatives*.
  Aspen Institute.
- Wigmore, J. H. (1937). *The Science of Judicial Proof* (3rd ed.). Little,
  Brown.
