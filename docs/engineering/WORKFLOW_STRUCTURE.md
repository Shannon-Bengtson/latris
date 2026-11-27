# Workflow structure: stages, steps and tracks

*Proposed 2026-11-27. Built: the registry, the steps on analyses and edit
operations (#60), and the places of every command, route and help topic
(#63), and reports and model-type help grouped by step (#62). The rest is
tracked in
[#60](https://github.com/Shannon-Bengtson/latris/issues/60),
[#61](https://github.com/Shannon-Bengtson/latris/issues/61),
[#62](https://github.com/Shannon-Bengtson/latris/issues/62) and
[#63](https://github.com/Shannon-Bengtson/latris/issues/63).*

One structure that every surface reads: the CLI, the server, reports, help,
editors built on the server, and chat tools. Today the modelling stages are
written down separately in several places, and nothing below a stage is
named, so each surface groups things its own way or not at all.

## Why

- latris registers 38 kinds of analysis result and 57 per-model-type edit
  operations. They are named by model type and method (`monte_carlo_sd`,
  `psa_markov`, `set_ft_uncertainty`), so the same step appears under many
  names.
- Surfaces that need to group them guess from names. The values checkpoint
  matches the word "sensitivity" and misses 7 of 9 sensitivity analyses
  (#61).
- Reports and generated analysis forms list results in registration order.
  Help topics use four different headings for the same kind of analysis.
- The stages themselves are defined in four places: the checkpoints
  (`operations/checkpoints.py`), the readiness transitions
  (`operations/readiness.py`), the help topics' categories, and each
  editor's own list.

## The structure

Three kinds of thing, each a fixed list:

- A **stage** is a phase of modelling, in order.
- A **step** is a part of one stage.
- A **track** runs alongside every stage. It holds what can happen at any
  point: citing a source, challenging a link, saving a version.

Everything a person or an agent can do sits at exactly one place: a track, a
step, or a stage as a whole (when it serves every step of that stage, like
listing a stage's recorded results). Names are technical nouns, the same
everywhere a person reads them. Ids are short.

### Stages and steps

| Stage | Step | Id | What it covers |
|---|---|---|---|
| **Frame** | Question and scope | `frame.question` | The question, the decision it informs, the boundary |
| | Audience | `frame.audience` | Who reads the result and what they will push on |
| | Model type selection | `frame.model_type` | Which model types, and why |
| **Build** | Structure | `build.structure` | Factors, links, polarity, descriptions, which elements each model type includes |
| **Formalise** | Definitions | `formalise.definitions` | Which elements a model type has, what kind each is, model-wide settings |
| | Values | `formalise.values` | Quantities on elements: probabilities, tables, equations, payoffs, weights, ratings |
| | Ranges | `formalise.ranges` | How uncertain each value is, and correlations between them |
| | Scenarios | `formalise.scenarios` | Named sets of alternative values |
| **Analyse** | Structural analysis | `analyse.structural` | What the model's shape implies, with no values: loops, paths, identification |
| | Base-case analysis | `analyse.base_case` | The model's result from the values as set |
| | Option comparison | `analyse.options` | Which of the options a person could choose is better |
| | Uncertainty analysis | `analyse.uncertainty` | How uncertain the result is |
| | Sensitivity analysis | `analyse.sensitivity` | Which inputs drive the result |
| | Estimation from data | `analyse.estimation` | What a dataset says about an effect |
| **Interpret** | Findings | `interpret.findings` | Claims the results support |
| | Interpretation | `interpret.interpretation` | The written sections: answer, confidence, limits, open questions |
| **Communicate** | Report | `communicate.report` | The report and its exports |
| | Diagram | `communicate.diagram` | The model's picture |
| | Sharing | `communicate.sharing` | Links to a model and copies of it, including the model as a file |
| **Use** | Contract | `use.contract` | The model's inputs and outputs, pinned to a version |
| | Prediction | `use.prediction` | Outputs for given inputs, from code or a pipeline |

A surface built on latris may register steps of its own under a stage (an
editor's presentation formats under Communicate, for example). It may not
add stages or tracks.

### Tracks

| Track | Id | What it acts on |
|---|---|---|
| AI assistance | `ai` | AI proposals and chains, and checkpoints |
| Evidence | `evidence` | Sources, citations, source checks, extracts, provenance records |
| Data | `data` | Datasets themselves: upload, cleaning, versions |
| Review and challenge | `review` | A person's judgment of the work: challenges, maturity, review packs, sign-offs |
| Verification and validation | `validation` | Tests of the model against a criterion: well-formedness, readiness, units, fit to data, refutation |
| Versions and history | `versions` | Milestones, alternatives, undo, comparing versions |
| Project | `project` | Everything that is not modelling: creating and opening projects, access and sync, display and layout, reference and help |

A **checkpoint** is where an AI building a model stops and asks the person
(`latris checkpoint show | record | skip | pace`), one per stage boundary.
Checkpoints exist only when an AI is building, so they are in the AI
assistance track, each tied to the stage it closes.

## Rules: how anything is placed

The lists are mutually exclusive and exhaustive because placement is a fixed
sequence of tests, not a judgment. Take the tests in order; the first that
holds decides, and the last in each sequence catches everything left. The
tests look at what an action acts on, writes and varies, never at its name
or its model type.

**Composite first.** An action that carries out several placed actions in
one call (building from a spec file, importing a model from another tool, a
chat tool that applies a batch of changes) has no place of its own. It
declares itself a composite, and each action inside it is placed by the
rules below.

**Track or stage**, by what the action acts on:

1. An AI proposal, chain or checkpoint → AI assistance.
2. A source, citation, source check or provenance record → Evidence.
3. A dataset itself (not an analysis that reads one) → Data.
4. A person's judgment of the work → Review and challenge.
5. A test of the model against a criterion, reporting whether it holds →
   Verification and validation.
6. A version, or the history → Versions and history.
7. Nothing in the model's content (the project, access, sync, display,
   reference) → Project.
8. Otherwise it is in a stage.

**Which stage**, by what the action writes or produces. Reading something
is placed with the thing read.

1. It serves the model to code (inputs in, outputs out) → Use.
2. It renders the model for a reader, or hands it over → Communicate.
3. It writes claims or text about results → Interpret.
4. It computes a result from the model, changing nothing in it (whether the
   result is recorded or not) → Analyse.
5. It writes a model type's own content → Formalise.
6. It writes the shared map → Build.
7. Otherwise: the project's question, scope, audience or choice of model
   types → Frame.

Test 4 is why fitting values from data (learning a Bayesian network's
tables, calibrating a simulation) is Formalise, not Analyse: it writes
values. An analysis that reads a dataset and records an estimate is
Analyse.

**Which Analyse step:**

1. It reads a dataset → Estimation from data.
2. It reads no values (only structure, definitions and evidence) →
   Structural analysis.
3. It compares alternatives a person could choose between (options,
   strategies, scenarios) → Option comparison.
4. It varies inputs one by one, or attributes the result's variation to each
   input → Sensitivity analysis.
5. It samples the uncertain inputs together and reports the spread of the
   result → Uncertainty analysis.
6. Otherwise: one result from the values as set → Base-case analysis.

**Which Formalise step:**

1. It stores a named alternative to values already set → Scenarios.
2. It says how uncertain a value is: a distribution, bounds, a correlation →
   Ranges.
3. It sets a quantity on one element of the model (a number, equation,
   table, rating or assessment on a factor, link, node, state or option) →
   Values.
4. Otherwise: which elements exist, what kind each is, and model-wide
   settings → Definitions.

An action with secondary outputs or mixed fields (a decision tree's
rollback also reports thresholds; an MCDA criterion has a direction and a
weight) is placed by the first test it meets, once.

## Where the terms come from

- **Uncertainty analysis and sensitivity analysis** follow Saltelli's
  definitions: uncertainty analysis characterises how uncertain the output
  is; sensitivity analysis apportions that uncertainty to the inputs. Health
  economics calls sampling the inputs "probabilistic sensitivity analysis";
  by these definitions it is uncertainty analysis, and reports and help say
  "also known as probabilistic sensitivity analysis".
- **Base-case analysis** is the health-economics and decision-analysis term
  for the result from the values as set. "Evaluation" is avoided: in
  modelling practice "model evaluation" means testing whether a model is fit
  for purpose.
- **Verification and validation** is the simulation-practice term for that
  testing, and every good-practice framework has a place for it (TRACE:
  implementation verification, model output verification, model output
  corroboration).
- **The stages** follow the sequence those frameworks share: problem
  formulation (Frame), conceptual model (Build), parameterisation
  (Formalise), model analysis (Analyse), and application (Use).
- **Values and Ranges** follow the ISPOR-SMDM modelling guidance, which
  treats point values and parameter uncertainty as one process and keeps
  structural uncertainty separate (here, alternatives in the Versions
  track).

Sources to cite when this is built: Saltelli et al. (2008, 2019) on
sensitivity analysis; Grimm et al. (2014) on TRACE; Briggs et al. (2012),
ISPOR-SMDM Task Force report 6.

## Classification

Each placement follows from the rules.

### Analyses (38 result kinds, plus three that record nothing)

| Step | Result kinds |
|---|---|
| Structural analysis | `toc-pathways`; and, recording no result, find loops, trace effects, causal identification |
| Base-case analysis | `sd-simulation`, `sd-loops`, `bn-query`, `bn-explanation`, `toc-process-trace`, `ft-analysis`, `bt-analysis`, `et-analysis`, `ach-analysis`, `argument-analysis`, `eq-evaluation`, `fcm-inference` |
| Option comparison | `mcda-analysis`, `dt-analysis`, `markov-analysis`, `sd-options`, `bn-options` |
| Uncertainty analysis | `sd-monte-carlo`, `bn-monte-carlo`, `ft-monte-carlo`, `bt-monte-carlo`, `et-monte-carlo`, `eq-monte-carlo`, `dt-psa`, `markov-psa` |
| Sensitivity analysis | `sd-sensitivity`, `bn-sensitivity`, `eq-sweep`, `sd-gsa`, `bn-gsa`, `ft-gsa`, `bt-gsa`, `et-gsa`, `dt-gsa`, `markov-gsa` |
| Estimation from data | `dag-estimate`, `toc-impact` |

1 + 12 + 5 + 8 + 10 + 2 = 38.

- MCDA, decision trees and Markov cost-effectiveness compare strategies, so
  they are option comparison. Competing hypotheses are not choices, so that
  analysis is base-case.
- Loop dominance and process tracing compute from values, so they are
  base-case, not structural.
- The argument-map analysis reads each claim's assessment, a value, so it is
  base-case.

### Formalise operations (57)

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
| Decision tree | settings, element, uncertainty (which chance nodes share one) | branch, payoff | correlation, range | |
| Markov | settings, element | transition, reward, start | correlation, range | |
| Argument map | element, link | claim | | |
| Equation model | | value, formula | uncertainty | scenario |

### Command groups

| Place | CLI commands today |
|---|---|
| Composite | `build` (from a spec) |
| AI assistance | `ai`, `checkpoint` |
| Evidence | `evidence`, `ref`, and the provenance records: `assumption`, `decision`, `question`, `exclusion`, `prediction`, `session` |
| Data | `data` |
| Review and challenge | `challenge`, `mature`, `signoff` |
| Verification and validation | `check`, `completeness` |
| Versions and history | `version`, `log`, `diff` |
| Project | `init`, `status`, `sync`, `docs`, `capabilities`, `foundations` |
| Frame | `project` (the foundation: question, scope, audience) |
| Build | `node`, `edge`, `attr`, `mapping`, `view` |
| Formalise, Analyse | each model type's group (`bn`, `sd`, `ft`…), by subcommand |
| Analyse | `analyse` (structural, and estimation), `results` (the stage as a whole) |
| Interpret | `finding`, `interpret` |
| Communicate | `export`, `link` |
| Use | `contract`, `predict` |

`elicit` (expert elicitation, partly built) needs no place of its own: a
session that sets values or ranges is Formalise, and its record of who said
what is Evidence.

## Does planned work fit?

Checked 2026-11-27 against every open issue and the roadmap. Nothing needs a
new stage, step or track.

| Planned | Place |
|---|---|
| New model types: influence diagrams (#42), structural equation models (#47), scenarios (#48), actor models (#49), realist CMO (#50) | Their operations and analyses fall into the existing Formalise and Analyse steps |
| BN ranked nodes (#44), continuous nodes (#53); SD arrays (#52), time-series forcing (#40); Markov time-varying transitions (#38); utility functions (#37); GSN vocabulary (#46) | Formalise: definitions or values |
| Correlated uncertainty (#36) | Formalise: ranges |
| SD calibration (#35), survival extrapolation (#51), fitting a path model (#47) | Formalise: values (they write values from data); their fit statistics are Verification and validation |
| Expected value of information (#43) | Sensitivity analysis when per input, uncertainty analysis when overall |
| MDP value iteration (#54) | Option comparison |
| Refutation tests (#54) | Verification and validation |
| Loop dominance for large models (#45) | Base-case analysis (unchanged) |
| Uncertainty bands on a prediction (#41) | Use: prediction |
| Import XMILE / Vensim (#39) | Composite |
| Share-link fidelity (#55) | Communicate: sharing |
| Elicitation in reports (#56) | Communicate: report |
| AI boundary prompts (#57), prompt caching (#58) | AI assistance |
| Per-cell history (#59) | Versions and history |

## How it is enforced

Everything a person or an agent can invoke declares its place, and a test
fails for anything that doesn't, or that uses an id not in the registry.

1. **The registry.** One module in `schema/` holds the stages, steps and
   tracks: id, name, order, one-line description. Nothing else spells them.
2. **Analyses.** `ResultKind` gains a required `step`.
3. **Edit operations.** `ChatOp` gains a required `step`.
4. **CLI commands and server routes.** Each module declares `PLACE`: one
   place, or a place per function with a module default
   (`operations/places.py`). A route built by a shared factory carries its
   own (`x-latris-place`), so `POST /api/mcda/analyse` is option comparison
   and `POST /api/ft/analyse` base-case. The server writes every route's
   place into its OpenAPI entry; `latris capabilities` lists every command
   with its place; the CLI reference opens with a generated index by place.
   A composite also declares what it can carry out (`CARRIES`).
5. **Help topics.** The header names a place (`place:`), by the topic's
   subject. Model-type topics are at model type selection, where people read
   what each type is for. The older free-text `category` stays until the app
   groups by place.
6. **Checkpoints and readiness.** Both read stages from the registry. The
   values checkpoint finds sensitivity analyses by step (fixes #61).
7. **Capabilities.** `latris capabilities` and `GET /api/analyses` serve the
   place with each entry, and the registry itself, so a surface generating
   from them groups the same way with no list of its own.

What does not change: CLI command names, routes, result-kind ids, the
package layout (one module per model type), and the method named in a
report's Methods section. A place is a label, not a rename.

One older label stays as it is, because it is stored in people's projects:

- **`AnalysisRun.purpose`** is recorded on every run in people's projects,
  with values from before this structure (Monte Carlo and MCDA runs are
  recorded as `sensitivity-analysis`). It is a stored format and isn't
  changed. A run's step comes from its result kind.

Readiness transitions name stages by registry id, from `frame → build` (they
started at `home`, the app's project landing, until the app showed Frame as a
stage; an app reading an older latris treats `home` as `frame`).

## What each surface does with it

- **Report.** Results grouped by step in the order above, step name as the
  heading, method in each result's own heading. A step with no results is
  left out. The analysis catalog lists analyses in the same order.
- **Help.** Every model-type topic heads its analyses with the step names,
  in order, with the method in parentheses ("Uncertainty analysis
  (probabilistic sensitivity analysis)"); a test keeps them aligned.
  Building a model stays under each topic's own headings. The workflow
  overview describes the seven stages and the tracks.
- **Editors.** Stage navigation, analysis forms and result lists come from
  the registry.
- **Chat tools.** Generated per step, not per model type and method, so the
  tool list is short and stops changing when a model type is added.
- **Usage data.** Events can be counted by place.

## Order of work

1. Registry, `step` on analyses and operations, tests, the checkpoint fix,
   capabilities (#60, #61).
2. CLI commands, routes and help topics declare theirs (#63).
3. Report grouping and help headings (#62).
4. Surfaces built on latris switch to reading it.
