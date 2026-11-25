# AI in latris: model library and learning loops

Design capture — 2026-11-25, extended same day with the telemetry chapter
after a tracking-surface audit of both repos. Two big directions for AI in
latris, the telemetry substrate that powers them, plus smaller items.
Companion to `docs/engineering/AI_LAYER.md` (which describes the current
layer); this document is forward-looking. The executable companion is
`docs/engineering/TELEMETRY.md`.

## What exists today (the ground we're building on)

- **Closed prompt library** — 45 canonical `PromptSpec`s (structured input,
  template, pydantic response model, mode). No open chatbox. Mutations only
  via validated proposals → `apply()` → human-attributed commit.
- **Interaction log** — `ai/interactions.jsonl` records every call with
  `adoption: approved/rejected/failed`, tokens, cost, target IDs. Its own
  docstring already promises "a future retrieval layer … to assemble context
  for the next call." Not built yet.
- **Rejected = memory** — rejected proposals are preserved and replayed to
  later prompts tagged `[REJECTED BY HUMAN]`. Captured, not yet learned from.
- **Value-conflict capture** — AI applies never clobber existing values;
  divergences are logged as questions (`_record_value_conflict`). Signal
  captured, not yet aggregated.
- **Checkpoints** — five phase-based stops where an agent must ask the
  person; the values checkpoint already picks questions using recorded
  sensitivity results. Answers land in `person-input.yaml`.
- **Access paths** — litellm calls, `ai task emit/apply` (bring-your-own-agent),
  agent-driven CLI with provenance guards, hosted chat connector, and plugin
  prompt registration (`latris.ai.registry`).
- **Chains** — fixed prompt sequences (`draft-model`, `find-connections`),
  step-at-a-time, pull-driven by the frontend.
- **Examples gallery** — `Shannon-Bengtson/latris-examples`: 10 verified,
  calibrated, fully-replicable models with real sources, built by
  `tools/build_all.py`, published as static artifacts via CI.

## Pillar 1 — The model library (publishable knowledge base)

**Vision.** Grow the examples gallery into a library that people publish to:
models as citable, reusable knowledge artifacts, not just demos. The library
is both a community asset and — crucially — a *retrieval substrate* that
makes the AI better.

**Components.**

- **Publishing flow.** A `latris publish`-style path from a local project to
  the library: manifest, license check, evidence check (sources with
  url/doi, as the gallery already enforces), rendered report + explorer
  artifacts, provenance intact. The gallery's `build_all.py` workflow is the
  prototype of this pipeline.
- **Quality signals.** What makes a library entry trustworthy: verified
  findings (no overclaims — the gallery's standard), calibration checks that
  ran clean, maturity ladder state, human review markers. These become
  library metadata, so "good model" is a computable property, not a vibe.
- **Motif retrieval.** `DraftConceptualModel` and `FindNewConnections`
  retrieve structurally similar models as few-shot exemplars. Because every
  latris model is git-backed YAML, "similar" can mean *graph-motif* similar
  (loop structures, pathway shapes, formalism idioms), not just embedding
  similar. Hard-won structural lessons (e.g. breaking an algebraic loop in a
  renewable-resource SD) become transferable.
- **Domain packs.** Curated bundles: foundational references, canonical
  fragments, and prompt packs (registered via `ai.registry`) for a domain —
  epidemiology, fisheries, security analysis. The registry already supports
  plugin prompts; packs extend that to knowledge.
- **Cross-formalism library.** The library spans all formalisms, so it can
  answer "how have people modelled *this kind of question* before?" and feed
  `RecommendApproach` with real precedent.

## Pillar 2 — Learning from usage (including how people use AI)

**Vision.** Collect information on how people use the system — modelling
behaviour and AI-proposal outcomes — so we can see exactly what works for
people and what doesn't, and so the AI itself improves. Two loops, with
different privacy postures.

### Loop A: per-project learning (local-first, no network)

Everything here runs on the project's own git-backed data. No telemetry
leaves the machine. This is the default and requires no consent machinery.

- **Retrieval layer for the interaction log.** Deliver the promised layer:
  query `interactions.jsonl` by target/attribute/prompt/adoption to assemble
  context for the next call — beyond today's same-target replay.
- **Rejection reasons.** Today rejection is a bare bit. Add an optional
  reason (small taxonomy: wrong-fact / wrong-granularity / wrong-scope /
  style / other + free text). Rejections become training signal about *this
  user's* taste.
- **Stance injection.** Distil recurring rejections and overrides into
  user-stance summaries injected into future prompts ("this user rejects
  per-element filler assumptions"; "prefers coarser granularity"). Same lever
  as the scope contract — which A/B showed beats prompt wording — but learned
  instead of declared.
- **Disagreement mining.** Aggregate `_record_value_conflict` events,
  overridden polarities, demoted evidence into a per-project disagreement
  map. Where AI and human systematically diverge, ask the person once,
  capture the answer as an assumption/constraint, inject it thereafter.
  Human corrections become model assets, not silent diffs.
- **Calibration tracking.** AI proposes confidence; later, elements get
  challenged, demoted, or survive. Git history + the log give an auditable
  calibration curve per project/prompt/model: "40% of my high-confidence
  structural claims here were later challenged." Feed it back into prompts —
  and into reports; it fits the evidence-native brand.

### Loop B: product-level learning (opt-in aggregation)

- **Prompt performance analytics.** Adoption rates per prompt, per model,
  per project — the data is already in the log. Turns the Flash-vs-Kimi
  bake-off from a one-off evaluation into continuous per-task model choice.
- **Prompt library improvement.** The prompt contract is deliberately a
  product asset; aggregated adoption/rejection-reason stats are the
  telemetry for improving it across releases.
- **Consent and privacy design (prerequisite).** Aggregation is strictly
  opt-in, anonymised, and never includes prompt text, model content, or
  identifiers — only outcome statistics. The local-first Loop A must be
  fully useful with Loop B switched off. This needs a design pass before any
  code.

### The quantitative bridge (the most latris-native idea)

- **Value-of-information-driven elicitation.** The AI's next question to the
  person should be the one whose answer most reduces decision-relevant
  uncertainty. latris already computes the ingredients: sensitivity rankings
  (SD/BN), EVPI (decision trees), recorded runs. Wire them to the elicitation
  interview and checkpoints so question selection is a computed quantity, not
  a vibe. This is where the quantitative engine and the LLM feed each other
  instead of taking turns.

## Telemetry — the long-term substrate

Telemetry is not a feature among the others; it is the substrate both pillars
stand on. The model library needs quality signals and usage rankings; Loop A
needs a richer interaction record; Loop B needs a data path at all. Design it
once, for the long term, and every later idea gets cheaper.

### What the 2026-11-25 audit found

**Exists (per-project, git-backed):** `ai/interactions.jsonl` (every AI call:
prompt, inputs, model, targets, adoption state, tokens, cost, errors — but no
timestamp on the record, no rejection reason, no surface, no post-hoc
outcome); `analysis/runs.jsonl` (every deterministic run with hyperparams,
metrics, duration); git itself as a full mutation audit trail with
`ai-proposed`/`human-authored` provenance; the provenance logs (challenges
with timestamped turns, checkpoint answers, signoffs).

**Exists (hosted, latris-app):** operational state only — accounts (with
self-declared role/industry/country), projects with activity timestamps,
share-link state, broker container sessions, and `ai_call_counts`, a daily
per-account counter that discards everything else about the call.

**Does not exist anywhere:** a behavioural event stream. No GUI
instrumentation, no MCP tool-call logging, no CLI usage events, no funnel
data, no edit-after-approve tracking, no way to answer "which of the 45
prompts actually help people?"

### Design stance

- **One event envelope, many event types.** A single append-only stream —
  `(id, ts, surface, event_type, actor_ref, project_id, payload_json)` — with
  a versioned pydantic registry for payloads. Extensibility comes from
  registering new event types, never from schema churn. This generalises the
  pattern `AIInteraction` and `AnalysisRun` already prove out.
- **Two tiers, one schema.** Local tier (per-project, in the latris repo —
  feeds Loop A, works offline, **never uploads without explicit opt-in** for
  the open-source CLI) and hosted tier (latris-app — feeds Loop B). Same
  envelope both sides; the hosted ingest endpoint just validates and stores.
- **Joinable by construction.** Events carry the IDs the system already
  mints: `AIInteraction.id`, `AnalysisRun.id`, `project_id`, `account_ref`
  (pseudonymised), session ids. The highest-value questions are joins:
  "approved proposals that survived 7 days unedited" = interaction log ⨝ git
  history.
- **Pseudonymous and aggregate-first.** Hosted events reference a hashed
  actor, never an email; reporting is aggregate-only; signup demographics
  (role/industry/country) are never joined to behavioural rows in exported
  views.

### Use-case horizons (why one flexible stream pays off)

1. **Product analytics (now).** Funnels (signup → first project → first
   analysis → first share), feature adoption across CLI/GUI/MCP, abandonment
   points (chains left mid-step, sessions dying at a checkpoint), retention.
2. **AI effectiveness (near).** Adoption rate per prompt and model;
   edit-after-approve rate (the real quality signal); rejection-reason
   distribution; cost per *adopted* proposal; calibration curves; continuous
   per-task model selection (the bake-off becomes a standing evaluation).
3. **AI learning substrate (the point of all this).** Every learning-loop
   item in Pillar 2 reads from this stream: stance injection, disagreement
   mining, calibration feedback. Longer term: exemplar ranking for motif
   retrieval ("which library models produce drafts people keep?"), evaluation
   of VoI question selection ("did the asked question reduce sensitivity
   rank?"), and curated few-shot/fine-tune datasets distilled from
   approved-only interactions — with the rejected ones as contrastive
   signal.
4. **Beyond the product (later, all free by-products).** Modelling-behaviour
   research (how do people actually build causal models — publishable, and
   on-brand for an evidence-native tool); methodology benchmark suites from
   real usage; pricing/packaging signals; capacity planning for the broker;
   support diagnostics; library community health.

## Smaller items

- **MCP prompts primitive.** Serve the 45 canonical prompts via MCP's
  first-class `prompts` (not just tools), so any MCP client sees the curated
  library natively, with `ai task emit/apply` as the execution path. Makes
  the closed library the standard interface rather than an app feature.
- **State-driven playbooks.** Chains that branch on model state instead of
  fixed sequences: after a draft, run `ScanEvidenceGaps`; cluster gaps →
  `CrossReferenceCheck`; coherence failure → `EdgeReclassify`. Readiness and
  maturity machinery already compute the state; the chain runner consults it.
- **"What changed" briefings.** Model diff + recorded runs over time → an
  AI-narrated digest ("since last session, posterior of X moved 30% after
  new evidence entered"). Extends the interpret prompts across time.
- **Fabrication telemetry.** The citation guard already refuses unknown
  bibkeys; logging refusal rates per model closes the hallucination loop.

## Standing guardrails (unchanged)

1. No AI-authored commits; the responsible human is always the git author.
2. Structured proposals only; `apply()` is the sole mutation path.
3. Closed prompt library; learning adapts *context*, not free-form behaviour.
4. Never fabricate citations.
5. Rejected proposals are memory — now upgraded to: rejections are *signal*.
6. Loop A is local-first and fully featured offline; Loop B is opt-in only.
7. Telemetry is pseudonymous, aggregate-first, self-built (no third-party
   analytics), and never a condition of using the open-source library; the
   CLI is excluded for v1, and if it ever joins it uploads nothing without
   explicit opt-in.

## Todos

### Pillar 1 — model library

- [ ] **L1.** Design doc: library publishing flow (`latris publish`), extending
      the gallery `build_all.py` pipeline — manifest, license/evidence checks,
      artifacts, provenance. (medium)
- [ ] **L2.** Library metadata schema: quality signals (verified findings,
      calibration status, maturity, review markers) as computable entry
      properties. (small)
- [ ] **L3.** Motif retrieval: index library models by graph structure +
      domain; few-shot `DraftConceptualModel`/`FindNewConnections` with the
      best matches. (large — flagship)
- [ ] **L4.** Domain packs: format for bundled references + fragments +
      registered prompts; pilot one domain. (medium)
- [ ] **L5.** Feed library precedent into `RecommendApproach`. (small,
      depends on L3)

### Pillar 2 — learning from usage

- [ ] **U1.** Retrieval layer for `interactions.jsonl` (query by
      target/attribute/prompt/adoption for context assembly). (medium —
      unlocks the rest)
- [ ] **U2.** Rejection-reason capture: optional taxonomy + free text on
      reject, schema + CLI/GUI surface. (small)
- [ ] **U3.** Stance injection: distill recurring rejections/overrides into
      user-stance summaries in prompt context. (medium, depends on U1+U2)
- [ ] **U4.** Disagreement map: aggregate value conflicts, polarity
      overrides, demotions; prompt-once-then-inject workflow. (medium)
- [ ] **U5.** Calibration tracking: AI confidence vs. later
      challenges/demotions; per-project curve; feed back into prompts and
      reports. (medium)
- [ ] **U6.** VoI-driven elicitation design doc: sensitivity/EVPI-ranked
      question selection for interviews and checkpoints. (small doc,
      large idea)
- [ ] **U7.** Consent/privacy design for opt-in aggregate telemetry
      (prerequisite for anything cross-project). (small doc — do first
      among product-level items)
- [ ] **U8.** Prompt performance analytics from logs (adoption per
      prompt/model); continuous model-choice evaluation. (medium,
      depends on U7 for any aggregation)

### Telemetry (see `docs/engineering/TELEMETRY.md` for the full plan)

- [ ] **T1.** Core event envelope + versioned payload registry in latris
      (`schema/events.py`); local append-only writer. (small — everything
      hangs off this)
- [ ] **T2.** Extend `AIInteraction`: timestamp, surface, session id,
      latency, optional rejection reason (folds in U2). (small)
- [ ] **T3.** ~~CLI instrumentation~~ — deferred (decision 2026-11-25: CLI
      excluded from telemetry for now; envelope keeps `surface="cli"`
      reserved for later).
- [ ] **T4.** Hosted telemetry service + ingest endpoint (latris-app:
      separate FastAPI service with its own SQLite, per 2026-11-25
      decision); broker middleware logging MCP tool calls (name, latency,
      outcome, account pseudonym, project). (medium)
- [ ] **T5.** GUI beacon client: batched feature/AI-lifecycle events.
      (medium)
- [ ] **T6.** Outcome sweeper: join interactions ⨝ git history →
      edit-after-approve, survival-at-7d, calibration inputs. (medium)
- [ ] **T7.** Aggregates/read models + internal dashboard. (medium)
- [ ] **T8.** Consent/privacy machinery: opt-in flags, pseudonymisation,
      retention, docs (folds in U7). (small doc + small code)

### Smaller items

- [ ] **S1.** Expose the prompt library via MCP `prompts` primitive. (small)
- [ ] **S2.** State-driven playbooks: chain runner branches on
      readiness/maturity state. (medium)
- [ ] **S3.** "What changed" briefing: model diff + runs → narrated digest.
      (small)
- [ ] **S4.** Log citation-guard refusal rates per model. (trivial)

### Suggested order

T1 → T2 first (telemetry plumbing; everything else reads from it), T4 in
parallel (separate service, latris-app), T5 once the ingest endpoint exists,
T6/T7 when data flows. T8 before the first ingest deploys (includes the
user's privacy-policy update). Then U1 → U3/U4 (the learning loop's visible
payoff), U6 as the design-doc flagship; L1/L2 early so the library has
something to grow from, L3 when the corpus justifies it; S1/S4 anytime
(cheap).
