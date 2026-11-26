# Workflow structure: stages, steps and tracks

*Proposed 2026-11-27. Not built. Tracked in
[#60](https://github.com/Shannon-Bengtson/latris/issues/60),
[#61](https://github.com/Shannon-Bengtson/latris/issues/61) and
[#62](https://github.com/Shannon-Bengtson/latris/issues/62).*

One structure that every surface reads: the CLI, the server, reports, help,
editors built on the server, and chat tools. Today the modelling stages are
written down separately in several places, and nothing below a stage is
named, so each surface groups things its own way or not at all.

## Why

- latris registers 38 kinds of analysis result and 57 per-model-type
  edit operations. They are named by model type and method
  (`monte_carlo_sd`, `psa_markov`, `set_ft_uncertainty`), so the same step
  appears under many names.
- Surfaces that need to group them guess from names. The values checkpoint
  matches the word "sensitivity" and misses 9 of 11 sensitivity analyses
  (#61).
- Reports and generated analysis forms list results in registration order.
  Help topics use four different headings for the same kind of analysis.
- The stages themselves are defined in four places: the checkpoints
  (`operations/checkpoints.py`), the readiness transitions
  (`operations/readiness.py`), the help topics' categories, and each
  editor's own list.

## The structure

Three kinds of thing, each with a fixed list:

- A **stage** is a phase of modelling, in order.
- A **step** is a part of one stage. Everything a person or an agent can do
  in a stage belongs to exactly one step.
- A **track** runs alongside every stage. It holds what can happen at any
  point: citing a source, challenging a link, saving a version.

Names are technical nouns ("Uncertainty analysis"), the same everywhere a
person reads them. Ids are short (`uncertainty`).

### Stages and steps

| Stage | Step | Id | What it covers |
|---|---|---|---|
| **Frame** | Question and scope | `frame.question` | The question, the decision it informs, the boundary |
| | Audience | `frame.audience` | Who reads the result and what they will push on |
| | Model type selection | `frame.model_type` | Which model types, and why |
| **Build** | Structure | `build.structure` | Factors, links, polarity, which elements each model type includes |
| **Formalise** | Definitions | `formalise.definitions` | What each element is: roles, states, gates, criteria, settings |
| | Values | `formalise.values` | Numbers and equations: probabilities, tables, rates, payoffs, weights, scores |
| | Ranges | `formalise.ranges` | How uncertain each value is, and correlations between them |
| | Scenarios | `formalise.scenarios` | Named sets of alternative values |
| **Analyse** | Structural analysis | `analyse.structural` | What the shape of the model implies: loops, paths, identification |
| | Evaluation | `analyse.evaluation` | The model's main result |
| | Option comparison | `analyse.options` | Which option is better, and by how much |
| | Uncertainty analysis | `analyse.uncertainty` | How sure the result is |
| | Sensitivity analysis | `analyse.sensitivity` | Which inputs drive the result |
| | Estimation from data | `analyse.estimation` | What a dataset says about an effect |
| **Interpret** | Findings | `interpret.findings` | Claims the results support |
| | Interpretation | `interpret.interpretation` | The written sections: answer, confidence, limits, open questions |
| **Communicate** | Report | `communicate.report` | The report and its exports |
| | Diagram | `communicate.diagram` | The model's picture |
| | Sharing | `communicate.sharing` | Links and copies of a model |
| **Use** | Contract | `use.contract` | The model's inputs and outputs, pinned to a version |
| | Prediction | `use.prediction` | Outputs for given inputs, from code or a pipeline |

Frame and Use are new as stages. Framing was "before building" in the
checkpoints, and the contract and `predict` had no stage.

A surface built on latris may add steps of its own to a stage through the
same registry (an editor's presentation formats under Communicate, for
example). It may not add stages.

### Tracks

| Track | Id | What it covers |
|---|---|---|
| Evidence | `evidence` | Sources, citations, source checks, extracts, provenance records |
| Data | `data` | Datasets: upload, operations, versions |
| Review and challenge | `review` | Challenges, maturity, review packs, sign-offs |
| Versions and history | `versions` | Milestones, alternatives, undo, comparing versions |
| AI assistance | `ai` | AI proposals and chains, and checkpoints |

A **checkpoint** is where an AI building a model stops and asks the person
(`latris checkpoint show | record | skip | pace`). There is one per stage
boundary: framing, structure, values, surprise, audience. The questions are
generated from the model, the answers are recorded in the person's words,
and the report says which were answered, skipped or never asked. They exist
only when an AI is building, so they sit in the AI assistance track, each
tied to the stage it closes.

Elicitation is left out until it is built.

## Classification

### Analyses (38 result kinds, plus three that record nothing)

| Step | Result kinds |
|---|---|
| Structural analysis | `sd-loops`, `toc-pathways`, `toc-process-trace`; and, recording no result, find loops, trace effects, causal identification |
| Evaluation | `sd-simulation`, `bn-query`, `bn-explanation`, `ft-analysis`, `bt-analysis`, `et-analysis`, `ach-analysis`, `argument-analysis`, `eq-evaluation`, `fcm-inference` |
| Option comparison | `mcda-analysis`, `dt-analysis`, `markov-analysis`, `sd-options`, `bn-options` |
| Uncertainty analysis | `sd-monte-carlo`, `bn-monte-carlo`, `ft-monte-carlo`, `bt-monte-carlo`, `et-monte-carlo`, `eq-monte-carlo`, `dt-psa`, `markov-psa` |
| Sensitivity analysis | `sd-sensitivity`, `bn-sensitivity`, `eq-sweep`, `sd-gsa`, `bn-gsa`, `ft-gsa`, `bt-gsa`, `et-gsa`, `dt-gsa`, `markov-gsa` |
| Estimation from data | `dag-estimate`, `toc-impact` |

10 + 5 + 8 + 10 + 3 + 2 = 38.

Decided: probabilistic sensitivity analysis is uncertainty analysis (it is a
Monte Carlo over the inputs; its outputs are the spread of the result and
acceptability curves). Analyses whose result is a choice between options are
option comparison, whatever the model type.

### Formalise operations

| Model type | Definitions | Values | Ranges | Scenarios |
|---|---|---|---|---|
| System dynamics | settings, role | initial value, constant, equation, table | uncertainty | scenario |
| Bayesian network | states | probability table, noisy-or | table uncertainty | scenario |
| Theory of change | level | prior, test | | |
| Fault tree | event, gate | probability | uncertainty | |
| Bow-tie | element, barrier | frequency | uncertainty | |
| Event tree | element, order, sequence | probability, frequency | uncertainty | |
| MCDA | element | criterion, score | | |
| Competing hypotheses | element, item | rating | | |
| Decision tree | settings, element | branch, payoff | uncertainty, correlation, range | |
| Markov | settings, element | transition, reward, start | correlation, range | |
| Argument map | element, link | claim | | |
| Equation model | | value, formula | uncertainty | scenario |

An operation that sets both what something is and a number (an MCDA
criterion's direction and weight, a decision-tree branch's label and
probability) is filed under Values: the rule is that anything setting a
number is Values.

## How it is enforced

Everything a person or an agent can invoke declares its step or track, and a
test fails for anything that doesn't, or that uses an id not in the list.

1. **The registry.** One module in `schema/` holds the stages, steps and
   tracks: id, name, order, one-line description. Nothing else spells them.
2. **Analyses.** `ResultKind` gains a required `step`.
3. **Edit operations.** `ChatOp` gains a required `step`.
4. **CLI commands and server routes.** Each declares a step or track.
   Commands and routes generated from a formalism inherit it from the
   analysis or operation they wrap.
5. **Help topics.** Front matter names a stage (and step, where the topic is
   about one) or a track, replacing today's free-text `category`.
6. **Checkpoints and readiness.** Both read stages from the registry instead
   of their own lists. The values checkpoint finds sensitivity analyses by
   step (fixes #61).
7. **Capabilities.** `latris capabilities` and `GET /api/analyses` serve the
   step with each entry, and the registry itself, so a surface generating
   from them groups the same way with no list of its own.

What does not change: CLI command names, routes, result-kind ids, the
package layout (still one module per model type), and the method named in a
report's Methods section. A step is a label, not a rename.

## What each surface does with it

- **Report.** Results grouped by step in the order above, step name as the
  heading, method in each result's own heading. A step with no results is
  left out.
- **Help.** Every model-type topic uses the step names as its headings, in
  order. The workflow overview lists the stages and steps once.
- **Editors.** Stage navigation, analysis forms and result lists come from
  the registry.
- **Chat tools.** Generated per step, not per model type and method, so the
  tool list is short and stops changing when a model type is added.
- **Usage data.** Events can be counted by step.

## Order of work

1. Registry, `step` on analyses and operations, tests, the checkpoint fix,
   capabilities (#60, #61).
2. CLI commands, routes and help topics declare theirs; report grouping;
   help headings (#62).
3. Surfaces built on latris switch to reading it.

## Open questions

- **Theory-of-change evidence tests** (`set_toc_test`) set probabilities, so
  they are under Values here. They are also evidence about a link. Values,
  or the Evidence track?
- **Argument maps** have no numbers. Their element and link operations are
  under Definitions and a claim's assessment under Values. Would all three
  be better in Build?
- **`argument-analysis`** ("does the conclusion stand?") is under
  Evaluation. Structural analysis is the other candidate.
- **`bn-explanation`** (most likely explanation) is under Evaluation.
- **Build has one step.** Splitting it (factors, links) adds little. Is one
  step acceptable, or does every stage need at least two?
- **Expected value of information** (#43), when built: sensitivity analysis,
  or a step of its own?
