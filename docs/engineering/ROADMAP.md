# Roadmap — model types and analysis layers

*Status: plan agreed 2026-11-16. The capability manifest (`latris
capabilities`, from `schema/model_types.py`) stays the machine-readable
truth for registered types; this page is the reasoning and the order of
work, including types that aren't registered yet.*

## Where we are

Fifteen model types are usable today, in seven method families (updated 2026-11-22). The pattern that
works is a **ladder** within each family — qualitative → semi-quantitative
→ quantitative, all on one shared substrate — so a model climbs a rung
without being redrawn. (These seven are the ladders of method in the table below. They are not the
three groups a model picker shows — `MODEL_FAMILIES` in `schema/model_types.py`: Causal & Systems
Thinking, Risk & Safety, Decisions & Evidence — which sort the same fifteen types more coarsely for
someone choosing one; a Bayesian network, for instance, sits on the causal-inference ladder here and
under Risk & Safety in the picker.)

| Family | Built | Missing rung |
|---|---|---|
| Systems | CLD → FCM → SD | — |
| Causal inference | DAG → effect estimation → BN | structural equation / path models (#11) |
| Evaluation | Theory of Change → process tracing → impact (ITS / DiD) | — |
| Risk and safety | Bow-tie → Fault tree / Event tree, with Monte Carlo | live links between them (today: citations); GSN |
| Decisions | MCDA; decision tree → Markov, with PSA, acceptability curves and (partial) EVPI | influence diagram (#10) |
| Arguments | ACH; argument map | GSN as a vocabulary over the argument map |
| Across types | Monte Carlo / PSA with correlated ranges; global sensitivity (Sobol, Morris); contract and predict for equation models, SD and BN (#17) | predict for the risk and decision types; uncertainty bands on a prediction |
| Equations | Equation model: sourced formulas with units, no clock (#18) | time-series forcing for SD (#19); lookup tables, global sensitivity |

The last three types built (fault tree, bow-tie, event tree) came from the
registered roadmap list, which was assembled to test the schema's
extensibility rather than from user demand, and they serve the audience
least likely to adopt Latris (safety engineers have entrenched tools). They
are done and coherent; the safety track now pauses until a real safety user
appears. GSN waits for that; the argument map it builds on now exists.

## Principles for choosing

- **Fill missing rungs before adding families.** A rung reuses the family's
  substrate, evidence and reports; a new family starts cold.
- **Serve the audience we have** — analysts, evaluators, consultants and
  researchers defending a model to a board, client or reviewer.
- **Inspectable only.** Every number a person can source, check and
  challenge. Black-box ML, structure learning and agent-based models stay
  out (agent-based models: runnable, not inspectable — an explicit
  exclusion, not an omission).
- **Prefer pure Python or what's already installed.** The `quant` extra
  already brings `statsmodels`, `networkx`, `scipy` and `scikit-learn`; the
  Monte Carlo sampler and uncertainty schema exist; `MarkovSettings`
  (discounting, half-cycle correction) is already written. New dependencies
  must be compatible with Apache-2.0: `statsmodels`/`networkx` (BSD),
  `SALib`/`DoWhy`/`lifelines`/`PySD` (MIT) are fine; check `semopy`,
  `pyAgrum` and any MCDA package before adding; avoid `pm4py` (AGPL).
- **Ask what people actually bring.** Usage of app.latris.app and the
  connector outranks this list; revisit the order when we have it.

## Step 0 — make a new type cheap (done)

Each recent type touched the same dozen places (registry, readiness,
outcome handling, result kinds, CLI, routes, build spec, share link,
analysis replay, report, diagram, claims). Before adding ten more, they
plug in through one module per formalism (`operations/formalisms/`, see
[ARCHITECTURE.md](ARCHITECTURE.md) → "Adding a formalism"). Target: a Tier A
type in about half a day.

## Tier A — quick: pure Python or libraries already installed

| # | Model / layer | Answers | How | Effort |
|---|---|---|---|---|
| 1 | **Effect estimation on a DAG** | How big is the effect of X on Y? | `statsmodels` regression / GLM adjusting for the adjustment set the DAG already finds; gives the data workspace a job | 1–2 days |
| 2 | **MCDA** (options × weighted criteria) | Which option should we pick? | numpy: weighted sum, swing weights, rank-reversal sensitivity; AHP as an add-on (already named as future elicitation work) | 1 day |
| 3 | **ACH** — analysis of competing hypotheses | Which explanation does the evidence fail to rule out? | Heuer's consistency matrix and inconsistency scoring; reuses evidence checks and challenges | 1 day |
| 4 | **Decision tree** + EVPI | Best choice under uncertainty; is more information worth it? | Pure Python rollback; PSA through the existing sampler; EVPI on top | 2–3 days |
| 5 | **Markov cohort model** | What happens to a population over time, with costs and outcomes? | numpy; `MarkovSettings` exists. With #4: the health-economics (HTA) model | 2–3 days |
| 6 | **Bayesian process tracing** on ToC links | Given this evidence, how much more likely is this step? | Likelihood ratios per piece of evidence; hoop / smoking-gun / doubly-decisive / straw-in-the-wind tests (Van Evera; Befani & Mayne). The design is the work | 2–3 days |
| 7 | **Monte Carlo for FT / BT / ET** | How sure is that probability? | Existing uncertainty schema and sampler | ~1 day each |

## Tier B — about a week: a free library, or real design work

| # | Model / layer | How | Note |
|---|---|---|---|
| 8 | **Global sensitivity** (Sobol / Morris) across SD, BN, FT | `SALib` (MIT) | Cross-cutting analysis layer |
| 9 | **Interrupted time series / difference-in-differences** for ToC impact | `statsmodels` | The work is the validity guardrails |
| 10 | **Influence diagram** | Policy enumeration over a `pgmpy` BN for small models; or `pyAgrum` (check licence) | Follows #4 |
| 11 | **Structural equation / path models** | `semopy` (check licence) | Extends #1 to latent variables |
| 12 | **Argument map** (Toulmin / IBIS) | No library; reuses challenges and evidence | GSN then becomes a specialisation of it, settling GSN's open design question |
| 13 | **Scenarios**: cross-impact balance + morphological box | numpy | Foresight audience |
| 14 | **Actor models**: power–interest grid + network analysis | `networkx` | Gives the `actor` kind a use |
| 15 | **Realist CMO / outcome mapping** | Structure | Pairs with #6 |
| 16 | **Survival extrapolation** | `lifelines` (MIT) | Only with the HTA vertical (#4 + #5) |

## Priority — models that can be called (added 2026-11-22)

*High priority, ahead of the remaining Tier B items. Each needs a short design section in
[ARCHITECTURE.md](ARCHITECTURE.md) before code.*

Every run today is an analysis of the model as stored, and its result is recorded into the project
for the report. Nothing declares "these are the model's inputs, these are its outputs" or lets
another program call it. That closes off a whole use: a pipeline that loads one reviewed version of
a model from git and drives it with its own inputs (forcing). The same gap hides a kind of model
Latris should hold well: one built from physics or published parameterisations, where every
equation and coefficient has a source — among the most defensible models there are.

| # | Model / layer | Answers | How | Effort |
|---|---|---|---|---|
| 17 | **Predict** — an input/output contract and a stateless run (**first cut done**: `latris contract`, `latris predict`, `latris.load`; design in [PREDICT.md](PREDICT.md)) | Given these inputs, what does this version of the model say? | See below. Equation model, SD (values) and BN | built; follow-ups below |
| 18 | **Equation model** — quantities joined by sourced formulas, no clock (**done**: `latris eq`; design in [EQUATION_MODEL.md](EQUATION_MODEL.md)) | What does this physics / published parameterisation give for these inputs? | A formalism plugin reusing the SD expression evaluator (`_sd_eval.py`) and unit checker (`_units.py`), without the integrator; each formula and coefficient cites its source and stated range of validity | built |
| 19 | **Time-series forcing for SD** | What happens under this rainfall / demand / price record? | A series input declared in the contract and interpolated against `TIME`; today the only route is a hand-typed lookup table | 1–2 days after #17 |

**Predict (#17), in three parts:**

1. **A contract, committed with the model.** Named inputs (units, scalar or series, valid range)
   and named outputs. Derived where the formalism already knows the answer — SD constants and
   initial values, BN evidence nodes, equation-model inputs — and edited by a person where it
   doesn't.
2. **A stateless `predict` operation.** Takes a contract-shaped payload, returns the outputs, and
   writes nothing to the project. The result carries the model's commit and a hash of the
   contract, so every number a pipeline emits traces to one exact, reviewed version and the
   sources behind it.
3. **Pinned loading.** Load a project at a git ref (a tag, a reviewed checkpoint) and call it:
   from Python, the CLI and the server. The semantic diff reports a change to the contract
   separately from a change to the internals, so a pipeline knows whether an upgrade is safe.

**Guardrails:**

- **Out-of-range inputs are reported, not hidden.** A pipeline will send values outside what the
  evidence supports; predict returns a validity warning beside the number rather than clamping
  silently.
- **Forward evaluation only.** Calibration, parameter fitting and data assimilation are out of
  scope here.
- **Still inspectable.** This is not the "black-box predictors" of *Not doing*: every formula and
  parameter stays one a person can source, check and challenge.

## Tier C — easy, but needs a decision first

- **`DoWhy` (MIT)** — refutation tests on top of #1; heavy dependency, so
  `statsmodels` first.
- **MDP value iteration** — trivial maths, narrow audience.
- **Fishbone** — better as a CLD template than a type.
- **State machine, flowchart, Petri net, HMM** — weak fit with the causal
  and evidence core.

## Not doing

Agent-based models (`Mesa`), causal discovery / structure learning,
black-box predictors. (Predict, #17, runs inspectable models on new inputs; it is not a
black-box predictor.)

## Order of work

1. ~~**Step 0** — one-module-per-formalism refactor.~~ Done: `operations/formalisms/`.
2. **Quick wins** — #1 effect estimation (done: `latris analyse
   estimate`, an analysis layer on the DAG), #2 MCDA (done: `latris mcda`),
   #3 ACH (done: `latris ach`).
3. **Decisions + HTA** — #4 decision tree + EVPI (done: `latris dt`, with probabilistic
   sensitivity analysis: `dt range` and `dt psa`), #5 Markov (done: `latris markov`, with PSA,
   acceptability curves and EVPI: `markov range` and `markov psa`).
4. **Evaluation ladder** — #6 process tracing (done: `latris toc prior|test|trace`, an analysis on
   the theory of change), #9 ITS / DiD (done: `latris toc impact`).
5. **Analysis layers** — #7 Monte Carlo on the risk types (done: `latris ft|bowtie|et uncertainty`
   and `monte-carlo`), #8 global sensitivity (done: `latris analyse global-sensitivity`, Sobol and
   Morris over the risk types, decision trees, Markov, SD and BN; a set of probabilities — a BN
   table, a chance node's branches — is one grouped input). Built on numpy and scipy's Sobol
   sequence rather than SALib: the estimators are a few dozen lines (checked against the Ishigami
   function's analytic indices), and SALib would bring matplotlib, pandas and multiprocess.
6. **Argument map** (#12) (done: `latris argument`; design in
   [ARGUMENT_MAP.md](ARGUMENT_MAP.md)), then GSN on top of it — when a safety user appears.
7. **Models that can be called** (high priority) — #18 equation model first (done: `latris eq`, with
   scenarios, input sweeps and Monte Carlo). It was built ahead of predict because its kernel,
   `equation_model.compute`, is already the pure "values in, every quantity out" function predict
   wraps, and its inputs (units, valid ranges) and outputs are the contract in miniature. Then #17
   predict (first cut done: a contract per model type, a stateless run, pinned versions and the
   first public Python API, for the equation model, SD values and BN). Next for #17: uncertainty
   bands on a prediction, the risk and decision types, and the app's "use" view; then #19
   time-series forcing for SD, which waits until someone needs it. Small follow-ups to #18: lookup
   tables, and adding it to the global-sensitivity layer (#8).
8. **XMILE / Vensim import** (decided 2026-11-25 — the "off the roadmap" line in
   FOUNDATIONS.md is reversed): import SD models via `PySD` (MIT), the adoption
   lever for SD users with existing Stella/Vensim models. Before committing an
   implementation, validate real-world export fidelity (arrays/subscripts, lookup
   tables, units) on genuine Stella and Vensim files — Latris SD is scalar-only
   today, so the first importer defines the honest subset it accepts and refuses
   the rest loudly rather than degrading silently.

Registry statuses follow this plan: influence diagram is `roadmap`; GSN stays `roadmap`, now a
vocabulary over the argument map (ARGUMENT_MAP.md → "GSN, later"). MCDA, ACH, decision tree,
Markov, argument map and equation model are built. Process tracing is an analysis on the theory of
change, not a type of its own, so it isn't registered separately.
