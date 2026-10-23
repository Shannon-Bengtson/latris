# Schema notes

How design commitments become pydantic models and YAML files.

## Core principle

> File layout is the schema. One concern per file for diffs.

Every YAML file has exactly one pydantic root model. Models are pydantic v2,
`model_config = ConfigDict(extra="forbid")` by default so stray keys fail loud.

## Layer ownership: git vs. schema

The schema and git form a deliberate division of labour. **The schema
records what only the schema can know**; everything else is read from
git or from the entity's ULID. Honouring this rubric keeps the schema
small and the git history load-bearing.

| Concern | Owner | How to read |
|---|---|---|
| When a record was first written | **ULID** (intrinsic to the ID) | `id_timestamp(model.id)` |
| When a commit was made | **Git** | `commit_timestamp(sha, root)` in `repo/git.py` |
| Who committed a row | **Git** | `git log --format=%an,%ae` |
| Branch / version parentage | **Git** (commit graph + refs) | `repo/lineage_index.py` |
| Workflow gate state (`Maturity`) | **Schema** | `entity.maturity` |
| Evidence audit axes (`source_access`, `support_verdict`, `quote`) | **Schema** | `EvidenceLink` fields |
| Multi-actor lifecycle (`Informants`) | **Schema** | `entry.informants` |
| Semantic attribution diverging from commit author (`authored_by`, `raised_by`, `opened_by`) | **Schema** | dedicated fields — survive rebases/squashes/amends that would corrupt git author |
| Event timestamps semantically distinct from creation (`held_at`, `resolved_at`, `signed_at`, `at`, `updated_at`) | **Schema** | dedicated fields |

### What the schema deliberately does NOT carry

- `created_at` on records that have a ULID `id` — the ULID encodes the
  timestamp at millisecond precision; storing it twice is redundancy
  that can drift if writers populate the field after generating the
  ID. Use `id_timestamp(model.id)` at read time.
- `parent_id` / `parent_branch` on `LineageNode` — git already knows
  branch parentage. The lineage tree is materialised by walking refs
  and `git merge-base`, then enriched with the workflow-only fields
  (`name`, `maturity`, `relationship`, `notes`).
- Top-level `ProjectFoundation.created_at` / `updated_at` — the
  project IS the git repo; first commit is its creation, last commit
  is its update.

### What the schema deliberately DOES carry (despite a git equivalent)

- `authored_by` / `raised_by` / `opened_by` / `created_by` on log
  rows and milestones — semantic attribution can legitimately diverge
  from the commit author (e.g. Alice's notes are committed by Bob).
  Rebases, squashes, and amends would corrupt these if they were
  derived from `git log`.
- `Signoff.signed_at` — the timestamp IS the attestation event, which
  may be back-dated to match a workshop or review date.
- `Session.held_at` — workshop date, possibly past-dated relative to
  the record's creation.
- `InterpretSection.updated_at` — staleness signal; the moment prose
  was last regenerated, distinct from the section's first creation.

## Stable IDs

- **Scheme:** ULID (via `python-ulid`). Sortable, opaque, collision-safe.
- **Scope:** every Entity, Edge, Challenge, Assumption, Decision, Signoff,
  Session, Question, Exclusion, Prediction, AIInteraction gets a ULID.
- **Invariant:** IDs survive renames, retypes, and formalism changes.
  User-visible labels are display-only.
- **Format:** 26-char Crockford base32. Prefixed by kind in YAML for
  readability (`node_01H...`, `edge_01H...`) but the prefix is cosmetic and
  not part of the ID proper.

## Schema version

Lives at `.graph-tooling/version` in every project. Single integer. Bumped
when a breaking schema change lands. Loader refuses to open a project
whose version is newer than the installed tool.

**Current: v6** (was v5). v6 dropped redundant write-time timestamps
(``created_at``/``opened_at``/``raised_at``/``registered_at``/``run_at``/
``performed_at``/``timestamp``) from every model whose ``id`` is a ULID
— the ULID encodes the timestamp at millisecond precision, so the
field was duplicative. v6 also dropped ``LineageNode.parent_id`` /
``parent_branch`` (parentage now derived from git via
``repo/lineage_index.py``) and ``Dataset.content_hash`` (unused).
``ProjectFoundation.created_at`` / ``updated_at`` are likewise gone
— first-commit and HEAD-commit timestamps from git serve that role.
The v5 → v6 transition is a **hard break**: v5 projects don't load
into v6 tools. Demo projects in this repo were rewritten alongside
the schema change.

## Entity → file map

| Design term | Pydantic model | On-disk file |
|---|---|---|
| Project foundation | `ProjectFoundation` | `project.yaml` |
| Research base refs | `ReferenceLibrary` | `research-base/references.bib` |
| Research notes | *(Markdown, free-form)* | `research-base/notes.md` |
| Substrate (L2) | `Substrate` | `substrate/conceptual.yaml` |
| Attribute: description | `AttributeSet[str]` | `substrate/attributes/descriptions.yaml` |
| Attribute: confidence | `AttributeSet[Confidence]` | `substrate/attributes/confidence.yaml` |
| Attribute: polarity | `AttributeSet[Polarity]` | `substrate/attributes/polarity.yaml` |
| Evidence links | `EvidenceLinkSet` | `substrate/attributes/evidence-links.yaml` |
| Layer 2 ↔ 3 mapping | `MappingRegistry` | `substrate/mappings.yaml` |
| Any formal view (CLD, DAG, FCM, …) | `View` (single class; `kind` validated against `MODEL_TYPE_REGISTRY`) | `views/{kind}.yaml` |
| Assumptions | `AssumptionLog` | `provenance/assumptions.yaml` |
| Decisions | `DecisionLog` | `provenance/decisions.yaml` |
| Signoffs | `SignoffLog` | `provenance/signoffs.yaml` |
| Sessions | `SessionLog` | `provenance/sessions.yaml` |
| Questions | `QuestionLog` | `provenance/questions.yaml` |
| Exclusions | `ExclusionLog` | `provenance/exclusions.yaml` |
| Predictions | `PredictionLog` | `provenance/predictions.yaml` |
| Challenges | `ChallengeLog` | `ai/challenges.yaml` |
| AI interactions | `AIInteraction` (one per line) | `ai/interactions.jsonl` |
| AI project context | *(Markdown, free-form)* | `ai/project-context.md` |
| Layout (excluded from semantic diff) | `LayoutFile` | `layout/<view>.layout.yaml` |
| Elicitation index | `ElicitationLog` | `provenance/elicitations.yaml` |
| Per-session elicitation | `ElicitationSession` | `provenance/elicitations/<YYYY-MM-DD>-<slug>.yaml` |
| View roles | `ViewRoleMap` | `views/roles/{view_kind}-roles.yaml` | **built** |
| Model settings | `SDSettings` / `FCMSettings` / `MarkovSettings` | `views/settings/{model_type}-settings.yaml` | **built** (schema) |
| Parameter uncertainty | `ParameterUncertaintySet` | `substrate/attributes/parameter-uncertainty.yaml` | **built** (schema) |
| Datasets | `DatasetLibrary` | `data/datasets.yaml` | **built** |
| Committed dataset files | *(arbitrary content)* | `data/files/<name>` | **built** |
| Dataset action log | `DataActionLog` | `data/actions/{dataset_id}.yaml` | **built** |
| Dataset versions | `DatasetVersionLibrary` | `data/versions.yaml` | **built** |
| Analysis runs | `AnalysisRun` (one per line) | `analysis/runs.jsonl` | schema only |
| Analysis outputs | *(arbitrary)* | `analysis/outputs/<run_id>/...` |
| BN CPTs | `BNCPTFile` | `views/parameters/bn-cpt.yaml` |
| SD equations (flows + auxiliaries) | `SDEquationSet` | `views/parameters/sd-equations.yaml` |
| SD stock initial values | `SDStockSet` | `views/parameters/sd-initial_value.yaml` |
| SD constants | `SDConstantSet` | `views/parameters/sd-constant.yaml` |
| SD table functions | `SDTableSet` | `views/parameters/sd-table.yaml` |
| SD classification (stock/flow/auxiliary/constant/source_sink) | `RoleSet` | `views/roles/sd-roles.yaml` |
| Markov / MDP transitions | `MarkovTransitionsFile` | `views/parameters/markov-transitions.yaml` |
| SCM coefficients | `DAGCoefficientsFile` | `views/parameters/dag-coefficients.yaml` |
| Fault-tree event probs | `FTEventProbsFile` | `views/parameters/ft-event-probs.yaml` |
| Node state spaces | `NodeStateSpacesFile` | `views/parameters/node-state-spaces.yaml` |

**Parameterized views and the analysis layer.** The `views/parameters/*`
files hold the quantification of a structure the modeller already drew —
e.g. `dag-coefficients.yaml` carries regression coefficients (the
**Regression** model type is a DAG whose edges have fitted/elicited
magnitudes). Each parameter cell is provenance-bearing and challengeable,
which is what keeps these models inside the inspectability test (see
[`ARCHITECTURE.md`](ARCHITECTURE.md) → Layer 3). `ParameterUncertaintySet`
annotates any such cell with a distribution; **Monte Carlo / PSA / EVPI**
is a cross-cutting *analysis layer* that propagates those uncertainties
over any parameterized model (BN, regression, SD, …) — it is not itself a
model type or a parameter file. See the PARAMETERS design spec (held in the private design docs).

## Maturity ladder

`Maturity = Literal["proposed", "reviewed", "approved"]`, applied
uniformly to `Entity`, `Edge`, `Finding`, `Mapping`, `LineageNode`,
and `Milestone`. The single chokepoint is
`operations/maturity.py`: `propose()`, `mark_reviewed()`,
`approve()` (atomically writes a `Signoff` row), and
`compute_badges()` (derived badges for has-evidence /
has-challenges / has-formalism / has-quantification /
has-confirmed-prediction). Attribute entries do not carry their
own maturity — the parent entity/edge owns it. Per-cell
uncertainty lives in `Confidence` and the `EvidenceLink`
audit axes. Full design in the MATURITY_LADDER design spec (held in the private design docs).

## Evidence attaches to attributes, not entities

This is a load-bearing concept-doc commitment. `EvidenceLink` keys by
`(target_id, attribute_name) → list[Citation]`, not by `target_id` alone.

## Informants list

Every attribute carries a list of informants with roles:
`proposed_by`, `extended_by`, `contested_by`, `approved_by`. Each entry is
an `Actor` — `HumanActor` (name + optional email), `AIActor` (model id),
or `ExpertActor` (see "Expert as actor" below). Used by the semantic
diff to show who touched what.

## Expert as actor

`ExpertActor` is a sibling of `HumanActor` and `AIActor`, distinguished
by `kind="expert"`, carrying `name`, `email`, `credentials`,
`affiliation`, and an optional `calibration_score` populated by
protocols that calibrate (e.g. Cooke's classical method). It is the
right type when someone participates not as the modeller but as a
domain authority being elicited from. Full design in the ELICITATION
design spec (held in the private design docs).

## Provenance origin and verification axes

Every `AttributeValue`, `Entity`, `Edge`, `EvidenceLink`, and
quantitative parameter cell carries two orthogonal provenance fields:

```
ProvenanceOrigin       = human-direct | human-elicited | ai-proposed
                       | data-derived | imported | mixed
ProvenanceVerification = unverified   | ai-verified   | human-verified
```

Default is `human-direct` / `unverified` so existing data is
backwards-compatible. The split exists because the same value can be
(say) data-derived but human-verified, or AI-proposed but
human-verified, and conflating the two loses audit signal.

## Source-id reference pattern

Every cell that didn't come from `human-direct` carries a
`source_id: str | None` pointing to the originating record in the
appropriate log:

| Origin | Pointer target |
|---|---|
| `human-elicited` | `ElicitationSession.id` (in `provenance/elicitations/...`) |
| `ai-proposed` | `AIInteraction.id` (in `ai/interactions.jsonl`) |
| `data-derived` | `AnalysisRun.id` (in `analysis/runs.jsonl`) |
| `human-direct` / `imported` | `null` |

This is polymorphic by convention — the field is just a string, and
the target log to look in is determined by `origin`. The future
`latris` library will resolve these via
`session.source_record()` / `cell.source_record()` etc.

## First-class data and analysis objects

Two top-level concerns have their own files. **Datasets are fully built;
AnalysisRun is schema-stubbed only.**

- **`Dataset`** (in `data/datasets.yaml`) — **built.** Structured input
  that algorithms read. Includes `DatasetLibrary` (registration +
  `ColumnSpec` metadata: name, dtype, role, description),
  `DataActionLog` (per-dataset audit trail of all operations), and
  `DatasetVersionLibrary` (named snapshots at git commits). 39 pandas
  operations across 4 categories (cleaning, transform, feature
  engineering, reshaping) via `operations/_data_engine.py`. Upload,
  versioning with restore, column metadata editing, and preview/stats
  all work end-to-end. GUI data view with `ColumnInspector`, `DataTable`,
  `DataToolbar`.
- **`AnalysisRun`** (append-only in `analysis/runs.jsonl`) — **schema
  only.** An algorithm execution recording purpose, algorithm, library
  version, hyperparameters, seed, input dataset(s), input substrate
  commit, outputs, metrics, and what was changed. Distinct from
  `AIInteraction`, which is an LLM call.

Full design in the DATA_AND_ANALYSIS design spec (held in the private design docs).

## Quantitative parameters per view

Per-formalism parameter files live under `views/parameters/`:
`bn-cpt.yaml`, `sd-equations.yaml`, `markov-transitions.yaml`,
`dag-coefficients.yaml`, `ft-event-probs.yaml`, plus shared
`node-state-spaces.yaml`. Each parameter cell is keyed
`(target_id, parameter_name, ...)` and carries the same `origin /
verification / source_id / informants` machinery as attributes —
so a CPT row produced by SHELF elicitation, fitted from data, or
typed in by hand all coexist with full per-row audit. Validation
(does every required cell exist? does it conform to the view's
constraints?) lands as the `compile <view>` command. Full design in the
PARAMETERS design spec (held in the private design docs).

## On-disk format is ours, by design

The substrate, attribute, parameter, elicitation, dataset, and
analysis-run schemas are all designed for the future `latris`
Python library to read efficiently — not for pgmpy-pickle
compatibility, NetworkX JSON interchange, or XMILE round-trip. Users
who need an external format get one-way `latris export
<format>` escape hatches, clearly labelled as dumps. This is a
deliberate moat decision; rationale in the LIBRARY design spec (held in the private design docs).

## PDF storage policy

PDFs do not version well in Git. V1 ships a **references-only** policy:
`references.bib` entries link to PDFs the user already has (typically in
Zotero or a local cache). The repository does not commit PDF files. This
keeps repos small and diffs clean. Git LFS and hybrid policies remain
options for later versions.

## Contested / minority views

First-class. A `contested: bool` flag + a sibling `contested_views: list[...]`
on attributes. Never silently overwritten; resolution requires going through
`operations/challenges`.

## Known schema backlog

The "data-driven backlog" entries have progressed:
- **Provenance-axis split** — **done** (M11). `ProvenanceOrigin` (6
  values) × `ProvenanceVerification` (3 values) on entities, edges,
  attribute values, evidence links.
- **`Dataset`** — **done.** Full data wrangling system (schema, 39 ops,
  versioning, audit trail).
- **`AnalysisRun`** — **schema stubbed only.** Implementation deferred
  to M17+.

Open backlog items:

- **Per-cell history retrieval API.** On-disk schema records only
  the *current* origin/source for each cell. The future
  `latris` library exposes `attribute.history()` /
  `cell.history()` reconstructed from git. Library-side; no schema
  change.
- **Model type registry evolution.** The `ModelTypeSpec` registry
  (built) defines 4 stable (CLD, DAG, FCM, BN) + 16 planned model types. Registry-driven
  activation (`operations/activation.py`) eliminates scattered dicts:
  each model type registers view class, validators, attribute handlers,
  and settings in a single call. When planned types become stable,
  they add one `activate_model_type()` call in `_activations.py`.
  View role layer (`schema/roles.py`) assigns formalism-specific
  entity classifications without touching the substrate `EntityKind`.
  Model settings schemas (`schema/settings.py`) define per-formalism
  simulation parameters (SD, FCM, Markov built; others as needed).

## Extensibility hypothesis — other formalisms in the same lingua franca

**Premise.** The substrate (Layer 2) is a typed graph with stable IDs,
attributes, evidence per attribute, provenance logs, and challenge
workflows. Several model classes outside the v1 roadmap (CLD / DAG / BN
structure / fault trees / bow ties) plausibly fit the same architecture
with **additive** changes only — no schema migration. We've designed for
that explicitly: `EntityKind` (7 substrate values: concept, variable,
event, actor, state, decision, hazard) and `EdgeKind` (12 values) are
`Literal[...]` enums and new view kinds inherit from `_ViewBase`.
**Formalism-specific entity classifications** (stock, chance, goal, gate,
barrier, place, transition, etc.) live in a separate **view role layer**
(`schema/roles.py` + `operations/view_roles.py`), not in the substrate
`EntityKind`. This keeps the substrate vocabulary universal while letting
each formalism assign its own semantic roles. Each future formalism adds
a role mapping and (if needed) a `ViewX` with its own constraint validator.

**Registered formalisms** — 5 stable types (CLD, DAG, FCM, BN, SD) and 15
planned types are declared in the `ModelTypeSpec` registry with their
structural validators and required entity/edge kinds. Planned types are
visible for readiness guidance but are not switchable until promoted.
Being registered is not the same as being on the roadmap: of the planned
types, only fault tree, event tree, bow-tie, GSN and theory of change are
currently on it. Decision tree, influence diagram and Markov/MDP are
parked; causal DAG is being folded into DAG; the rest are not currently
planned (their fit notes are kept below for reference).

| Class | Registry status | Notes on fit |
|---|---|---|
| **BN** | Stable | Discrete Bayesian Network engine built: state spaces + CPTs with per-cell provenance, exact inference (pgmpy), Noisy-OR, parameter learning, sensitivity analysis. |
| **SD** | Stable | Stock-and-flow engine built: stock/flow/auxiliary/constant/source_sink as view roles (no EntityKind change); `flow` edges carry material, `causal` edges are information links; per-parameter provenance; equations evaluated on pint quantities so dimensional consistency is enforced by arithmetic; table functions; deterministic simulation via scipy `solve_ivp` (hand-rolled Euler). |
| **Causal DAG** | Registered — merging into DAG | Quantitative extension of DAG; parameter schemas designed. |
| **GSN / safety cases** | Registered — on the roadmap | Strong fit. Adds `goal`/`strategy`/`solution`/`context`/`justification` as view roles; `solved_by`/`in_context_of` to EdgeKind. Provenance layer lands as core, not nice-to-have. Surfaces the assumption-as-node design question (see below). Largest commercial upside. |
| **Bow-Tie / Fault Tree** | Registered — on the roadmap | Risk/safety analysis. Fault tree uses `gate` view role + `logical` EdgeKind; bow-tie uses `barrier`/`hazard` view roles. |
| **Petri nets** | Registered — not currently planned | Adds `place`/`transition` as view roles, plus a bipartite view-level constraint. Tokens / firing semantics are runtime, not structural. |
| **Markov chains / MDPs** | Registered — parked | `state` and `decision` in substrate EntityKind; `utility` as view role for rewards. Transition probabilities deferred to quantitative track. Model settings schema (`MarkovSettings`) built. |
| **Influence Diagram** | Registered — parked | Extends BN with `decision`, `chance`, `utility` view roles and `informational` edges. Standard decision-analysis formalism. |
| **Decision Tree** | Registered — parked | Sequential decision/chance branching to outcome nodes. Acyclic tree. |
| **Event Tree** | Registered — on the roadmap | Forward-logic complement to fault trees. Barrier success/failure branching. |
| **Fishbone / Ishikawa** | Registered — not currently planned | Root cause analysis with categorised cause branches. Acyclic tree. |
| **Theory of Change** | Registered — on the roadmap | Logic model: activities → outputs → outcomes → goals. Policy/evaluation standard. |
| **Argument Map** | Registered — not currently planned | Toulmin/IBIS argumentation. Claims, warrants, rebuttals. Partial structural overlap with GSN. |
| **Fuzzy Cognitive Map** | Stable | CLD with continuous edge weights in [−1, +1]. Cycles allowed; weight storage and steady-state inference are built. |
| **Flowchart** | Registered — not currently planned | Activity-decision-outcome process flow. Universal visual modelling tool. |
| **State Machine** | Registered — not currently planned | States and guarded transitions. Qualitative sibling of Markov. |

**Open question if we ever wire GSN.** GSN treats Assumptions and
Justifications as **substrate nodes** (connectable by edges to Goals).
We currently treat them as **provenance log entries** (separate files,
not connectable by edges). For CLD / BN / SD work the log model is
correct ("we're treating this rate as constant" is narration about the
model, not part of it). For GSN it isn't. The two can coexist —
assumption-as-node lives in substrate, assumption-as-log captures
rationale + maturity — but resolving how they relate is best done
*after* a worked GSN example exists. Don't pre-decide.

**Why these are registered but not built.** Registration as `planned`
declares intent and plants the EntityKind/EdgeKind vocabulary early,
but none are switchable until their constraint validators and
model-specific attributes are wired into the readiness engine. The risk
of building wrong without a real user in front of us is much higher
than the cost of refactoring later — and the refactor is bounded
because the relevant fields are deliberately Literal-typed for additive
extension. Concrete next move flagged in `ROADMAP.md` deferred section:
have a 30-minute conversation with a safety engineer (rail / aerospace
/ medtech in AU/NZ) before building any of the safety formalisms.

## Schema readiness for future capabilities

Most future capabilities in the product roadmap backlog
(assertions, staleness, structural influence, refactoring ops, branch
comparison) are queries or operations over the existing schema — no
schema changes needed. Two concerns worth noting for future
implementers:

**Cross-project import concern for `source_id`.** When the `source_id`
pattern lands (M11), it points to provenance records
(`ElicitationSession`, `AnalysisRun`, `AIInteraction`) within the same
project. Future composable sub-model import would bring elements from
another project whose `source_id` pointers won't resolve locally.
Simplest design: import copies the referenced provenance records
alongside the imported elements, keeping `source_id` a project-local
pointer. Alternative: extend to `(project_uri, source_id)`. Either
works; the "copy alongside" approach is lower-complexity. Don't
pre-build; just note here so M11 doesn't close the door.

**Branch comparison uses same IDs.** Within-project branch comparison
(the primary model-differencing use case) does NOT need semantic
matching — the same ULIDs exist across branches because they share
history. The existing `diff/semantic.py` engine already compares
commits structurally. Ghost-overlay of connections from other branches
is a UI concern, not a schema concern.

## Deterministic serialisation

`repo/yaml_io.py` sorts mappings by **insertion order of the pydantic model**
(not alphabetical) so re-saving a file never reorders. Lists of entities are
sorted by ULID ascending on save — ULIDs are time-sortable, so this preserves
authoring order while giving us a canonical form for diffs.
