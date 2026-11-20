# Architecture

## Three-layer architecture

The architecture is a **three-layer model** with a separate mapping
registry, not a single universal graph. The earlier framing — "every model
type shares the same structural skeleton" — is partly right and partly an
elegant lie. Many formalisms share a graph-shaped substrate and a common
reasoning/evidence workflow, but CLDs, BNs, causal DAGs, system dynamics,
bow ties, and fault trees have **different formal semantics that matter
early**.

### Layer 1 — Universal substrate (the actual moat)

Meta-information *about* modelling, not *of* the model. This layer is
universal because evidence that "community trust" affects "compliance" is a
claim supported by citations and review, regardless of whether it appears as
a CLD edge, a BN arc, or a bow-tie threat pathway.

Contents: project foundation, entity identity, citations/evidence, relational
provenance (informants), challenge logs, contested/minority views,
assumptions, decisions, sign-offs, sessions, questions, exclusions,
predictions register, maturity state per attribute, version history
(Git-backed), AI interaction history, generated pack content.

Incumbents do not offer this layer at all, in any formalism.

### Layer 2 — Typed conceptual layer (the lingua franca)

A **structured pre-formal model**: general enough to sit upstream of any
specific formalism, but disciplined enough that downstream formalisation is
not a fantasy. It is not a CLD. It is not a free-form concept map. It is a
controlled, typed conceptual graph with node types, relation types,
directionality status, formalisability flags, and definitions.

Three design principles: (1) evolvable ontology (file format supports
migration), (2) typed, not loose (not a glorified Miro board), (3)
pre-formal, not informal (where *structured reasoning* preceding a model
lives).

### Layer 3 — Formal model views (projections, not conversions)

Each formalism is a **projection** of the conceptual layer — a disciplined
derivation that enforces the formalism's own rules. "Projection" is
deliberately different from "conversion": projections drop, specialise,
split, and merge nodes as needed.

Layer-3 membership is governed by the **inspectability test** (Latris
principle 5 — a formal view belongs only if every step of its reasoning
can be inspected, evidenced, challenged, and defended): This admits both *structural* views
(the graph is the model) and *parameterized-but-legible* views (structure
plus fitted/elicited numbers, where each coefficient is itself a
defensible claim — e.g. regression). It excludes black-box predictors
(random forests, gradient boosting, neural nets) by design — they are
runnable but not inspectable. Monte Carlo / PSA / EVPI is a cross-cutting
*analysis layer* over any parameterized view, not a view in this table.

| Formal view | What the projection enforces / adds | Status |
|---|---|---|
| Concept map | Raw conceptual layer rendered directly | v1 qualitative |
| CLD | Polarity (+/-); cycles allowed; loop detection + classification, polarity propagation, centrality | v1 qualitative |
| DAG (incl. BN structure, causal-DAG structure) | Acyclicity; directionality mandatory; d-separation, Markov blanket, path enumeration, adjustment sets | v1 qualitative |
| BN quantitative | State spaces, CPTs, inference | stable (built) |
| SD quantitative | Stocks, flows, auxiliaries, constants (view roles); unit-checked equations (pint); table functions; deterministic ODE simulation (scipy) | stable (built) |
| Causal DAG with identification | Observed/unobserved, adjustment sets | merging into DAG |
| Regression (linear/logistic/GLM) | DAG with fitted/elicited edge coefficients; quantifies DAG edges | not currently planned |
| Markov Cohort Model | States and strategies (roles); per-strategy transition probabilities on links, per-state costs and utilities; cohort trace, discounting, half-cycle correction, incremental cost-effectiveness (ICERs, dominance, NMB) | stable (built) |
| Influence Diagram | Decision + chance + utility nodes, informational arcs | on the roadmap |
| Decision Tree | Decision, chance and terminal nodes (roles); branches as links with labels, probabilities and values; rollback to the optimal strategy, EVPI per uncertainty, probability thresholds | stable (built) |
| Event Tree | Initiating event → ordered yes/no headings → end states (roles; tree stored as data and checked complete); conditional branch probabilities, sequence and end-state frequencies | stable (built) |
| Fishbone / Ishikawa | Categorised cause branches converging on effect | not currently planned |
| Theory of Change | Input → activity → output → short/long-term outcome → impact levels (view roles); acyclic, forward-only results chain; pathway enumeration with per-link evidence status and assumptions | stable (built) |
| Argument Map | Toulmin/IBIS claims, warrants, rebuttals | on the roadmap |
| Fuzzy Cognitive Map | CLD with edge weights in [−1, +1]; steady-state inference | v1 semi-quantitative |
| Flowchart | Activity-decision-outcome process flow | not currently planned |
| State Machine | States and guarded transitions | not currently planned |
| Bow-Tie | Threat → prevention barriers → top event → mitigation barriers → consequence, escalation factors and their controls (view roles); barrier type/status/owner/PFD; line flags and LOPA frequencies | stable (built) |
| Fault Tree | Top event → gates (AND / OR / k-of-n vote, stored on the event) → basic events (view roles); minimal cut sets, exact top-event probability (BDD), Birnbaum / Fussell–Vesely / RAW importance with provenance | stable (built) |
| Petri Net | Bipartite places + transitions, token semantics | not currently planned |
| MCDA | Options × criteria (roles); swing weights, directions and scales; additive value ranking, dominance, weight rank-reversal thresholds | stable (built) |
| ACH | Hypotheses × evidence items (roles); CC–II ratings, credibility and relevance; weighted inconsistency, diagnosticity, linchpins with source checks | stable (built) |

### Mapping registry

Cross-formalism coherence is maintained by an explicit **mapping registry**
— a first-class data-model object, not implicit identity. Expected
cardinalities: one-to-many, many-to-one, and one-to-none are normal.
AI proposes mappings; human approves/edits.

Membership default: every factor and link is in every chosen model type
(`views.auto_project` maps what isn't mapped yet when a type is opened)
unless a person leaves it out. Leaving out is recorded in the registry
(`MappingRegistry.left_out`, with an optional reason) so auto-projection
never undoes it; mapping the element again clears it. A view holds a link
only with both its ends.

### Continuity, not portability

The right frame is **continuity**, not portability. What carries forward:
conceptual identity, evidence, provenance, challenge logs, assumptions,
version history. What requires human judgement on projection: directionality,
node role, semantic commitments. What doesn't carry forward: quantitative
parameters, formalism-specific constraints.

> **Many modelling workflows share an upstream conceptual structuring phase,
> and almost no tools preserve that phase — along with its evidence,
> reasoning, and review history — in a continuous, auditable way across
> downstream formal models. This tool does.**

### What git owns vs. what the schema owns

Because the substrate is git-backed, the schema deliberately delegates
to git anything git already carries: write timestamps (via ULIDs),
commit authors, branch parentage, and version history. The schema
records what only the schema can know: workflow gates (Maturity),
evidence audit axes, multi-actor lifecycle (Informants), and event
timestamps semantically distinct from creation. The full rubric lives
in [`SCHEMA_NOTES.md`](./SCHEMA_NOTES.md) → "Layer ownership: git vs.
schema".

---

## Repository layout (modelling project)

```
project-name/
├── project.yaml                   # problem statement, schema version, config
├── research-base/
│   ├── references.yaml            # reference library (primary evidence store)
│   ├── references.bib             # reserved for BibTeX import/export (created empty)
│   └── notes.md                   # user research notes
├── substrate/
│   ├── conceptual.yaml            # Layer 2 lingua franca: entities + edges
│   ├── attributes/                # per-entity attributes, one file per type
│   │   ├── descriptions.yaml
│   │   ├── confidence.yaml
│   │   ├── polarity.yaml
│   │   ├── evidence-links.yaml    # the claim layer
│   │   └── data-links.yaml        # data-derived provenance
│   └── mappings.yaml              # mapping registry (Layer 2 ↔ Layer 3)
├── views/
│   ├── cld.yaml                   # CLD projection
│   ├── dag.yaml                   # DAG projection
│   └── parameters/                # quantitative (v2): bn-cpt.yaml, etc.
├── data/                          # dataset management
│   ├── datasets.yaml              # DatasetLibrary (all registered datasets)
│   ├── versions.yaml              # DatasetVersionLibrary (all snapshots)
│   ├── files/                     # raw CSV/TSV files by dataset name
│   └── actions/                   # per-dataset audit logs (JSONL per dataset)
│       └── {dataset_id}.jsonl     # DataActionLog
├── analysis/                      # analysis outputs + interpretation
│   ├── findings.jsonl             # append-only findings log
│   ├── interpretation.yaml        # InterpretSection content
│   ├── runs.jsonl                 # AnalysisRun records (operations/analysis_runs.py)
│   ├── outputs/<run_id>.json      # recorded results (operations/analysis_results.py)
│   └── report.yaml                # results hidden from reports
├── layout/                        # excluded from semantic diffs
│   ├── conceptual.layout.yaml
│   ├── cld.layout.yaml
│   └── dag.layout.yaml
├── provenance/
│   ├── assumptions.yaml
│   ├── decisions.yaml
│   ├── signoffs.yaml
│   ├── sessions.yaml
│   ├── questions.yaml
│   ├── exclusions.yaml
│   ├── predictions.yaml
│   ├── review-sessions.yaml       # ReviewSession lifecycle records
│   └── elicitations/              # per-session files
├── ai/
│   ├── interactions.jsonl         # append-only AI log
│   ├── challenges.yaml
│   └── project-context.md
├── reports/
│   ├── draft.md
│   └── exports/                   # git-ignored by default
└── .graph-tooling/
    ├── version                    # schema version, for migrations
    ├── lineage-node.yaml          # current version metadata
    └── milestones.yaml            # milestone log for current branch
```

Layout is a separate top-level folder (GeNIe's insight extended to separate
files). Attributes are split per type for targeted diffs. The AI interaction
log is append-only JSONL for clean Git appends. Reports are tracked; exports
are disposable.

---

## The CLI ↔ GUI boundary contract

The Latris app (developed in the private app repo) reuses this core
through the Python API server. To keep that possible, the CLI remains
deliberately thin:

> A CLI command is one parse + one call into `operations/` + one print.
> No business logic in `cli/`.

The GUI's Python API server imports `operations/` directly. Same invariants,
same tests, same schema. See "GUI architecture" below for how the app
talks to the server.

## Module layout

```
src/latris/
├── schema/            # pydantic v2 models — the data contracts
│   ├── project.py     # project.yaml (foundation: research_question | decision)
│   ├── substrate.py   # conceptual.yaml (entities + edges), mappings.yaml
│   ├── attributes.py  # descriptions / confidence / polarity / evidence-links / data-links
│   ├── views.py       # one View shape for every kind (kind checked against the registry)
│   ├── provenance.py  # 8 provenance object types
│   ├── ai.py          # challenges.yaml, interactions.jsonl record
│   ├── references.py  # extended BibTeX entries
│   ├── datasets.py    # Dataset, ColumnSpec, DatasetLibrary
│   ├── data_actions.py # DataAction, DataActionLog (audit trail)
│   ├── data_versions.py # DatasetVersion, DatasetVersionLibrary
│   ├── lineage.py     # LineageNode, Milestone, MilestoneLog
│   ├── model_types.py # ModelTypeSpec registry (CLD, DAG, FCM, BN, SD, ToC, FT, BT, ET, MCDA, ACH, DT, Markov stable; 9 planned)
│   ├── roles.py       # ViewRoleMap — formalism-specific entity classifications
│   ├── settings.py    # Per-model-type settings (SDSettings, FCMSettings, MarkovSettings)
│   ├── common.py      # HumanActor, AIActor, ExpertActor, provenance axes
│   ├── ids.py         # ULID-based stable IDs
│   ├── interpretation.py # InterpretSection, section types, audience targeting
│   ├── review.py      # ReviewManifest, ReviewFeedbackItem, ReviewSession
│   ├── findings.py    # Finding, FindingCategory, FindingStatus
│   ├── analysis.py    # AnalysisRun (schema only)
│   └── elicitation.py # ElicitationSession, ElicitationProtocol
├── repo/              # on-disk project handling
│   ├── layout.py      # canonical directory shape — single source of truth (~30 properties)
│   ├── project.py     # Project.load/save/validate
│   ├── yaml_io.py     # the ONLY place that reads/writes YAML
│   └── git.py         # the ONLY place that shells out to git
├── operations/        # pure business logic — CLI and GUI both call here
│   ├── init.py, nodes.py, edges.py, attributes.py
│   ├── evidence.py, challenges.py, provenance.py, views.py
│   ├── mappings.py, lineage.py, elicitation.py
│   ├── datasets.py    # upload, apply_operation, versioning, preview
│   ├── references.py  # CRUD, BibTeX import, DOI import, Semantic Scholar search
│   ├── readiness.py   # per-model-type readiness assessment
│   ├── graph_analysis.py # pure CLD loop / DAG structural analysis algorithms
│   ├── activation.py  # registry-driven model type dispatch
│   ├── _activations.py # model type registrations (CLD, DAG)
│   ├── formalisms/    # one plugin module per model type (every stable type) — see "Adding a formalism"
│   ├── view_roles.py  # formalism-specific entity role operations
│   ├── _data_engine.py # pandas engine: 39 operations, stats, preview
│   ├── _resolve.py, batch.py
│   ├── commit.py      # the ONLY place that creates commits
│   ├── compose.py     # Gather→Build bridge: node/edge suggestions from data, refs, AI
│   ├── configure.py   # batch view-attribute configuration (Analyse phase)
│   ├── interpret.py   # interpretation section CRUD (Interpret phase)
│   ├── interpret_registry.py # per-model-type section specs
│   ├── findings.py    # findings lifecycle (JSONL append-only)
│   ├── fcm_inference.py # FCM steady-state computation (pure functions)
│   ├── view_attributes.py # model-type-scoped attribute queries/mutations
│   ├── project.py     # project-level operations
│   ├── _attribute_helpers.py # shared attribute upsert logic
│   └── _graph_checks.py # graph validation helpers
├── diff/              # model-aware diff
│   └── semantic.py
├── exporters/
│   ├── dot.py         # Graphviz DOT
│   ├── markdown.py    # markdown report
│   ├── mermaid.py     # Mermaid sketch embedded in the markdown report
│   ├── narrative.py   # AI-assisted prose narrative
│   └── packs.py       # pack configuration and assembly
├── ai/                # 46 canonical prompts, all wired
│   ├── prompts.py     # PromptSpec library (46 entries)
│   ├── call.py        # end-to-end orchestrator
│   ├── context.py, proposals.py, interactions.py
│   ├── credentials.py, config.py
│   └── adapters/      # ChatAdapter protocol + mock + litellm
├── server/            # FastAPI + WebSocket backend for the GUI
│   ├── app.py, deps.py, state.py, watch.py, help.py
│   └── routes/        # 27 route modules by domain
├── testing/           # example projects per model type (in the wheel) for apps' contract tests
└── cli/               # Typer app — thin
    ├── app.py         # root + --version + doctor
    └── *_cmd.py       # one module per command group
```

## Adding a formalism

Every model type (the causal types, SD, BN, Theory of Change, fault tree, bow-tie, event tree, MCDA, ACH,
decision tree, Markov) plugs in through **one module** in `src/latris/operations/formalisms/`. It
declares a `Formalism` with the hooks the shared code calls:

| Hook | Used by |
|---|---|
| `structure_problems`, `validators` (name → gap types), `whole_label` | readiness (`_STRUCTURAL_VALIDATORS`) |
| `outcome_role`, `outcome_refusal`, `outcome_ids`, `set_outcome` | `view_roles.set_role`, interpretation, `build --spec` `outcome:` |
| `claims(paths, section)`, `centrality`, `own_implications`, `sensitivity_fallback` | interpretation claims |
| `results` (`ResultKind`: kind, title, `render`, analysis, `run`, `definition`), `fingerprint_files` | `analysis_results` (report order, staleness), the report's Results section, `analysis_replay` (build-spec analyses and share links) |
| `ResultKind.tool` (`ChatTool`: name, description) | the chat tool latris-app generates for the analysis (options: its `SpecAnalysis` model, documented in `ANALYSIS_OPTION_DOCS`) |
| `ResultKind.charts` + `chart_kinds` (every kind it may emit), `needs_dataset` | the report's `latris-chart` markers; the surface manifest (`latris capabilities --surface`) that apps built on latris read |
| `spec_field`, `spec_check`, `spec_apply`, `spec_export` | `build --spec` and share links |
| `spec_info` | what applying the values tells the author (`build`'s `info`, e.g. which factors an SD equation reads), shown in chat after the operation |
| `mermaid` (full diagram) or `mermaid_groups` (columns) | the report's diagram |
| `cli` (module, command), `routes` (module) | `cli/app.py`, `server/app.py` |
| `whole_map`, `parameterised_nodes`, `connected_structure`, `empty_scope_gap` | `membership` (the whole map, or the factors a quantified type computes on), Build's connectivity gate, readiness |
| `source_label`, `scope_noun`, `loop_claims`, `acyclicity_claims`, `feedback_via_stocks`, `findings_priority` | interpretation wording and claims |
| `link_attribute` (the value its links carry: CLD polarity, FCM weight) | the AI context; `formalisms.attribute_home("polarity")` tells exporters where polarity is stored |
| `diagram_direction`, `polarity_labels` | the generic Mermaid and DOT sketches |
| `scenario_store` | result staleness when a run used saved scenarios |
| `ResultKind.superseded_by_wider` | which runs reports show (a newer run over a wider scope replaces an older one) |

Shared code never tests a model type's id: `tests/test_no_type_branches.py` fails on a branch such as
`model_type == "sd"` outside the type's own modules — add a field here instead.

Four things stay central on purpose, because each is a single registry or a
static schema:

1. the `ModelTypeSpec` in `schema/model_types.py` (availability, roles,
   validator names);
2. its build-spec block — a pydantic field on `BuildSpec`
   (`schema/build_spec.py`), and a model per analysis kind (only its own options), added to the
   `SpecAnalysis` union;
3. its entry in the foundations registry (`operations/foundations.py`);
4. its help topic (`server/help.py`), and its keys in `latris build --help`.

The steps for a new type: schema for its parameters (with round-trip tests)
→ its operations module (setters, structure check, analysis, `record`; storage through
`operations/_view_store.ViewStore` — load, `replace_entry`, `save` + commit, roles,
`resolve_factor` — and `EntryBase.is_weak` for unverified or contested numbers) →
CLI and routes modules → the plugin module, added to `_MODULES` in
`formalisms/__init__.py` (registration order = the order commands, routes
and report sections appear in) → the four central entries → tests and the
worked example → an example project in `latris/testing/examples/` that
records every new result kind. `tests/operations/test_formalisms.py` and
`tests/testing/test_examples.py` fail, naming what is missing, if a stable
type is half-wired — including a chart kind emitted but not declared, or a
result kind no example records.

**Surfaces built on latris.** Apps (the hosted report, share links, chat
connectors) don't keep their own lists of model types: they read the
surface manifest (`latris capabilities --surface`,
`operations/capabilities.build_surface_manifest`) — per stable type, its
build-spec block and JSON schema, its result kinds, chart kinds and which
results need a dataset — and test against `latris.testing`, whose
`example_payloads()` builds the example projects and returns every recorded
payload. A new type then reaches them, or fails their tests, when they pin
the release that has it.

Every stable type is registered: the causal types (CLD, DAG, FCM) from
`formalisms/causal.py`. They are made of the substrate itself, so they have no
build-spec block or command group of their own.

**Declared, not branched.** Shared code never tests a type's name. What sets a
type apart is a field on its `Formalism`, read by the shared code: `scope_noun`,
`loop_claims`, `acyclicity_claims`, `findings_priority`, `feedback_via_stocks`,
`parameterised_nodes`, `scenario_store`, `diagram_direction`,
`polarity_labels`, plus the hooks above. `tests/operations/test_no_type_branches.py`
fails on a comparison against a model-type id in `operations/` or `exporters/`
outside a type's own modules.

**The chat surface is declared too.** Each `ResultKind` declares its `tool`
(`ChatTool`: the chat tool that runs it) and each formalism its `chat_ops`
(`ChatOp`: one write operation per part of its build-spec block). latris-app
generates its chat connector's analysis tools and `apply_changes` operations
from the surface manifest, so a new type reaches chat with no app code.

## The five chokepoint files

Tight single-source-of-truth helps correctness stay tractable:

| File | Monopoly on |
|---|---|
| `repo/layout.py` | Every known path inside a modelling project |
| `repo/yaml_io.py` | All YAML reads and writes |
| `repo/git.py` | All `subprocess` calls to `git` |
| `operations/commit.py` | All commit creation + identity enforcement |
| `schema/ids.py` | All ID generation |

If you're touching one of these, pause and think — changes ripple.

## Data flow for a typical mutation

```
user types:           latris edge add A B --kind causal
                              │
cli/edge_cmd.py        parses args, calls...
                              │
operations/edges.py    Project.load() → mutate substrate → Project.save()
                              │
operations/commit.py   identity guard → stage → commit with semantic message
                              │
repo/git.py            subprocess.run(["git", ...])
```

Every mutation follows this shape. The CLI layer never calls `yaml_io`,
`git.py`, or `commit.py` directly — only through `operations/`.

## Why `src/` layout

Prevents accidental imports from a partially-installed working copy and
matches modern Python packaging conventions. `hatchling` picks it up via
`[tool.hatch.build.targets.wheel] packages = ["src/latris"]`.

## Open enums by design — `EntityKind`, `EdgeKind`, view kinds

`schema/substrate.py` defines `EntityKind` (7 values: concept,
variable, event, actor, state, decision, hazard) and `EdgeKind`
(12 values) as `Literal[...]` enums; `schema/views.py` keeps view kinds
open via `_ViewBase` subclasses. **Formalism-specific entity
classifications** (stock, chance, goal, gate, barrier, etc.) live in a
separate **view role layer** (`schema/roles.py` +
`operations/view_roles.py`) — not in the substrate. This keeps the
substrate vocabulary universal while letting each formalism assign its
own semantic roles to substrate entities. 9 planned model types are
registered in the `ModelTypeSpec` registry alongside the 13 stable ones
(CLD, DAG, FCM, BN, SD, Theory of Change, Fault Tree, Bow-Tie, Event Tree, MCDA, ACH, Decision Tree, Markov); the
Layer-3
table above gives
each one's
roadmap status. Each formalism lands as an **additive** extension — no
schema migration. See `SCHEMA_NOTES.md` → "Extensibility hypothesis"
for per-formalism fit notes and the open design question
(assumption-as-node vs assumption-as-log) that GSN would force.

## Built and future modules beyond the original M0–M10 plan

Several modules that were originally planned as future namespaces have
been built:

| Module | Status | Notes |
|--------|--------|-------|
| `operations/datasets.py` + `_data_engine.py` | **built** | Dataset registration, 39 pandas operations, versioning |
| `operations/references.py` | **built** | CRUD, BibTeX import, DOI import, Semantic Scholar search |
| `operations/lineage.py` | **built** | Milestones, alternatives, version tree |
| `operations/elicitation.py` | **built** | Session lifecycle, basic Q&A protocol |
| `operations/readiness.py` | **built** | Per-model-type readiness with structural validators |
| `operations/graph_analysis.py` | **built** | CLD loop analysis + DAG structural analysis (pure algorithms) |
| `operations/activation.py` + `_activations.py` | **built** | Registry-driven model type dispatch; single-call registration |
| `operations/formalisms/` | **built** | Formalism plugins: everything a newer model type adds (readiness, outcome, claims, results, build spec, share link, diagram, CLI and routes) in one module each |
| `operations/view_roles.py` + `schema/roles.py` | **built** | Formalism-specific entity role assignments |
| `schema/settings.py` | **built** | Per-model-type settings schemas (SD, FCM, Markov) |
| `operations/compose.py` | **built** | Gather→Build bridge: node/edge suggestions from data, refs, AI |
| `operations/interpret.py` + `interpret_registry.py` | **built** | Interpretation section CRUD, per-model-type section specs |
| `operations/findings.py` + `schema/findings.py` | **built** | Findings lifecycle: JSONL append-only, 6 categories |
| `schema/review.py` | **built** | Review pack data format (manifest, sessions). Export/import of the HTML pack is part of the Latris app |
| `operations/configure.py` | **built** | Batch view-attribute configuration for Analyse phase |
| `operations/fcm_inference.py` | **built** | FCM matrix-based steady-state, pure functions |
| `operations/view_attributes.py` | **built** | Model-type-scoped attribute queries and mutations |
| `schema/interpretation.py` | **built** | InterpretSection, audience targeting, staleness tracking |
| `exporters/narrative.py`, `packs.py`, `mermaid.py` | **built** | Report pipeline (prose, pack assembly, Mermaid sketch). Word, review-pack and story HTML exports moved to the Latris app (0.5.0), which adds them to the server through the `latris.server_plugins` hook |
| `operations/analysis_runs.py` + `analysis_results.py` | **built** | AnalysisRun log (`analysis/runs.jsonl`) and recorded results the report reads |

Still planned (not yet built):

```
src/latris/
├── compile/            # Validate parameter completeness; produce CompiledView
└── (existing modules unchanged)
```

When it lands, the chokepoints list extends:

| File | Monopoly on |
|---|---|
| `compile/validator.py` | All parameter-completeness checks against views |
| `compile/materialize.py` | Translation from on-disk parameter files to runtime backend objects (when the future `latris` library lands) |

`operations/analysis_runs.py` already holds the AnalysisRun monopoly: it is
the only place that writes `analysis/runs.jsonl` (results go through
`operations/analysis_results.py`).

## GUI architecture (React app + Python backend)

*Status: **built and shipping** as the Latris app, a React app in the
browser at `app.latris.app`, which lives in a separate private
repository. This repo is the backend it runs on: the same `latris`
package, same invariants, same schema. (Deployment details live with the
app repo.)*

The GUI is a **React frontend** talking to the **Python API server**
(FastAPI, `src/latris/server/`) that wraps `operations/` over HTTP and
WebSocket.

### Bridge layer

The server imports `operations/` directly: same invariants, same commit
model, same schema, same tests. The React frontend is purely rendering +
interaction. **No business logic leaves Python.**

```
React (browser)
     │ HTTP/WebSocket
     ▼
Python API server (FastAPI)
     │ direct import
     ▼
latris.operations
     │
     ▼
repo/ (yaml_io, git, layout)
```

### State model

Canonical state lives **on disk** (YAML files under the project tree).
React holds a **projected read cache** of the current model state. Every
mutation follows this flow:

1. User action in React (add node, drag edge, approve AI proposal)
2. API call to Python backend
3. `operations/` mutates on-disk files + auto-commits to git
4. Response returns updated state to React
5. React store updates its read cache

The Python backend is always the source of truth. The React state is
disposable — on reconnect, the frontend reloads from backend.

### Communication

- **HTTP** for request-response operations (add node, set attribute,
  resolve challenge, etc.)
- **WebSocket** for real-time push (file-change notifications,
  operation progress, AI streaming responses)

### Trust boundary

The server has no user accounts. It is safe to run where only its owner
can reach it, and must be gated anywhere else (the hosted app runs one
server per user session, in containers that share a host):

- **`LATRIS_SERVER_TOKEN`** — when set, every HTTP and WebSocket request
  except `/api/health` and CORS preflights must send
  `X-Latris-Token: <token>` (or `Authorization: Bearer <token>`); see
  `server/access.py`. The server warns at startup if it binds beyond
  loopback without one.
- **CORS** allows the localhost dev origins only — never `"null"`, which
  any web page can send from a sandboxed iframe.
- **Errors** return a message and an `error_id`; tracebacks go to the
  server log only.
- **User input never reaches code or arbitrary paths.** Dataset
  derived-column expressions are evaluated by a whitelisting AST walker
  (`operations/_safe_expr.py`), never `DataFrame.eval`. Dataset names,
  bibkeys and stored dataset locations are contained to their directories
  (`repo/layout.py`: `safe_filename_stem`, `contained_path`).
- **Outbound fetches of user/AI-supplied URLs** go through `_net_guard.py`:
  http(s) only, public addresses only (checked on every redirect hop),
  size-capped. `LATRIS_ALLOW_PRIVATE_FETCH=1` lifts the address check for
  a local install that needs an intranet source.

### File watching and CLI+GUI coexistence

Both the CLI and GUI operate on the same project files. The Python
backend watches project files for external changes (CLI use, manual
edits, git operations from another tool). Changes push to React via
WebSocket.

The CLI must work while the GUI is open — no file locking. Power users
will use CLI for scripted/batch operations and GUI for visual editing
in the same session.

### Undo / redo

Every `operations/` mutation auto-commits to git. Undo = `git revert
HEAD`. The bridge exposes this as an API endpoint. Ctrl+Z in the
React frontend calls the undo endpoint; the backend reverts and pushes
the updated state.

**Compound operations:** A GUI user dragging a node and connecting an
edge expects one undo step, not two. The `operations/` layer needs a
`batch()` context manager that groups multiple mutations into a single
git commit. This is an architectural concern, not just a UI concern —
the batch wrapper should be available to the library and CLI as well.

### Layout file persistence

Layout files under `layout/*.layout.yaml` remain **gitignored** for
semantic diff and merge sanity (see [`GIT_INTEGRATION.md`](GIT_INTEGRATION.md)).
The GUI persists node positions and sizes through `GET/PUT /api/layout`,
currently stored as `layout/canvas.layout.yaml`. Manual adjustment sticks
across sessions on the same project checkout, but layout is not part of the
auditable model state by default.

### What the GUI adds to the architecture

The CLI era contract ("GUI imports `operations/` directly") holds — the
FastAPI server does the importing. The React frontend adds a network
hop, but the invariants are identical. The server is a
thin adapter that translates HTTP/WebSocket calls into `operations/`
function calls. In practice, the server also owns:

- **State projection** (`server/state.py`) — loads all YAML/JSONL into
  a single dict, served at `GET /api/state`.
- **File watching** (`server/watch.py`) — detects CLI or external edits
  and pushes `state_changed` via WebSocket.
- **Layout persistence** — `GET/PUT /api/layout` stores canvas positions
  (separate from the git-tracked model data).
- **Readiness computation** — `GET /api/readiness` and
  `GET /api/model-types/readiness` compute scores from current state.

---

## CLI / library / GUI layering

The current `latris` CLI implements authoring (init, node add,
edge add, attr set, …) directly without going through a separate
library. That's correct for v0/M10. When the future `latris`
Python library lands (see the library design spec, held in the design
docs):

- The CLI becomes a thin shell over `latris.operations`,
  preserving its existing surface.
- The GUI's Python API server imports the same
  `latris.operations` — same invariants, same tests.
- External pipelines and notebooks `import latris`.

All three layers share one core. The CLI is one consumer; it isn't
the API.
