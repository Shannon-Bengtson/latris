# Roadmap — model types and analysis layers

*Status: plan agreed 2026-11-16. The capability manifest (`latris
capabilities`, from `schema/model_types.py`) stays the machine-readable
truth for registered types; this page is the reasoning and the order of
work, including types that aren't registered yet.*

## Where we are

Nine model types are usable today, in five families. The pattern that
works is a **ladder** within each family — qualitative → semi-quantitative
→ quantitative, all on one shared substrate — so a model climbs a rung
without being redrawn.

| Family | Built | Missing rung |
|---|---|---|
| Systems | CLD → FCM → SD | — |
| Causal inference | DAG → BN | **estimation**: "how big is the effect?" |
| Evaluation | Theory of Change | **testing the theory against evidence**, then **impact estimation** |
| Risk and safety | Bow-tie → Fault tree / Event tree | live links between them (today: citations) |
| Decisions | — | **the whole family** |
| Arguments | evidence checks and challenges, no formalism | **argument / hypothesis structure** |

The last three types built (fault tree, bow-tie, event tree) came from the
registered roadmap list, which was assembled to test the schema's
extensibility rather than from user demand, and they serve the audience
least likely to adopt Latris (safety engineers have entrenched tools). They
are done and coherent; the safety track now pauses until a real safety user
appears. GSN waits for that, and for the argument map below.

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

## Tier C — easy, but needs a decision first

- **Vensim / XMILE import via `PySD` (MIT)** — quick, and possibly the
  biggest adoption lever for SD users, but reverses "off the roadmap" in
  FOUNDATIONS.md.
- **`DoWhy` (MIT)** — refutation tests on top of #1; heavy dependency, so
  `statsmodels` first.
- **MDP value iteration** — trivial maths, narrow audience.
- **Fishbone** — better as a CLD template than a type.
- **State machine, flowchart, Petri net, HMM** — weak fit with the causal
  and evidence core.

## Not doing

Agent-based models (`Mesa`), causal discovery / structure learning,
black-box predictors.

## Order of work

1. ~~**Step 0** — one-module-per-formalism refactor.~~ Done: `operations/formalisms/`.
2. **Quick wins** — #1 effect estimation (done: `latris analyse
   estimate`, an analysis layer on the DAG), #2 MCDA (done: `latris mcda`),
   #3 ACH (done: `latris ach`).
3. **Decisions + HTA** — #4 decision tree + EVPI (done: `latris dt`; probabilistic sensitivity
   analysis still to come), #5 Markov (done: `latris markov`; PSA and
   acceptability curves still to come).
4. **Evaluation ladder** — #6 process tracing, #9 ITS / DiD.
5. **Analysis layers** — #7 Monte Carlo on the risk types, #8 SALib.
6. **Argument map** (#12), then GSN on top of it — when a safety user appears.

Registry statuses follow this plan: decision tree, Markov, influence
diagram and argument map are `roadmap`; GSN stays `roadmap` behind the
argument map. MCDA, ACH and process tracing aren't registered yet — each is
registered when it is built.
