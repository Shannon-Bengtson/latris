# AI layer

How `latris` actually talks to an LLM. Design notes so the CLI, GUI,
and any future surfaces can wire into the same primitives.

## Architectural commitments

The AI contract is **not customer-configurable**. It is a product asset,
thoroughly tested, updated with product releases. Getting it right is
non-trivial and is treated as a first-class design artefact alongside the
schema. See the product workflow spec (held in the private product docs)
for the product-level workflow rules, gates, and canonical prompt
descriptions.

The code honours five non-negotiables:

1. **No AI-authored commits.** Git author is always the responsible human.
   Every auto-commit flows through the identity guard.
2. **Structured edit proposals, not free-form mutation.** AI returns a
   pydantic-validated proposal; `apply()` is the *only* way it becomes a commit.
3. **Closed prompt library.** 46 canonical prompts; no open chatbox.
4. **Never fabricate citations.** `SuggestCitations` refuses unknown bibkeys
   at the apply layer regardless of what the model returned.
5. **Rejected proposals are memory.** The interaction log preserves them,
   clearly tagged, and the context assembler replays them labelled
   `[REJECTED BY HUMAN]`.

Product rule: AI should reduce the provenance burden, not increase it.
For field-level provenance and rationale work, the intended pattern is
AI drafts the value, the user approves/edits/rejects, and approval records
the origin and verification state automatically. The user should rarely
feel like they are filling out a separate provenance form.

### Provenance is captured at the point of the structural edit

The structural authors (`DraftConceptualModel`, `FindNewConnections`) capture
each node/edge's provenance **in the same call that proposes it**, split by
epistemic source:

- **Endogenous** — assumptions, edge polarity + rationale, confidence: knowledge
  the model already holds while reasoning about the element. The draft/edge
  schemas carry optional `assumptions`, `polarity`/`polarity_rationale`,
  `confidence` fields; `apply()` binds each to the created element's ID (an
  assumption can now attach to an *edge*, not just a node). Polarity + rationale
  are persisted together to the CLD view store (`_persist_edge_polarity`), so
  the coherence check lints one coherent story rather than fragments authored by
  different prompts at different times. Assumptions are **rubric-gated**: added
  only where an element rests on a non-obvious premise, never one-per-element —
  filler provenance is worse than an honest gap.
- **Exogenous, already-grounded** — `source_bibkeys`: when the model names a
  supplied reference an element came from, `apply()` turns it into an
  `existence` evidence link. Bibkeys absent from the library are skipped, never
  invented (same fabrication guard as `SuggestCitations`).
- **Exogenous, needs grounding** — net-new citations stay a separate, routine,
  **batched** pass (`CrossReferenceCheck` over every entity and edge), run
  before Analyse so the coherence gate and evidence-gap scan see populated
  provenance.

An `apply()` that touches many elements groups its writes into one commit via
`operations/batch.py` (nested batches defer to the outer one).

### AI mutations enrich, they don't clobber

A cross-cutting rule for every mutating AI call, split by what it writes:

- **Unique-valued attributes** (one value per element: `description`,
  `confidence`, `polarity`, `weight`) — an AI apply **never overwrites an
  existing value**. The write chokepoint `upsert_entry`
  (`operations/_attribute_helpers.py`) takes `preserve_existing=True` (threaded
  through `set_attribute` / `set_view_attribute` / `batch_set_view_attributes`)
  and returns `written` / `kept` / `conflict`. AI applies pass it True; human/CLI
  writes overwrite as before. On a **conflict** (AI disagrees with the existing
  value) the value is preserved and the divergence is logged as a question on the
  element (`_record_value_conflict`) — the signal is captured, not dropped. This
  is why re-running `SuggestEdgePolarities` fills only gaps and flags
  disagreements instead of clobbering co-authored polarities.
- **Collection provenance** (many per element: assumptions, evidence, questions,
  decisions, exclusions, contested-views) — the AI stays **free to keep adding**;
  there is deliberately no dedup barrier. Enriching provenance is the goal.
- **Transition prompts** (evidence verdict demote/promote, `EdgeReclassify`,
  edge remove, `ChallengeEdge`) are exempt — changing existing state is their
  purpose.

Mutating prompts are also **context-aware**: they see the existing value they
might set, the element's neighborhood (endpoint labels/kinds/descriptions), and
its provenance (assumptions/evidence), so they propose only what is genuinely
correct or missing (see `_build_suggest_edge_polarities`,
`_build_challenge_edge`).

### The scope contract

`ProjectFoundation` carries three optional prose fields —
`coverage_dimensions`, `granularity_level`, `audience` — plus the
(previously unused, now injected) `predictions`. When set, they flow into
**every** prompt's user message through the single `_foundation_summary`
helper, and the structural authors (`DraftConceptualModel`,
`FindNewConnections`, the extract/suggest node+edge prompts) are told to
**honour** them via `_SCOPE_CONTRACT_GUIDANCE` in their system prompt: span
every declared coverage dimension, match the stated granularity, frame for the
audience. This is the highest-leverage lever on structural consistency — a
real-AI A/B showed it moves run-to-run agreement and dimension coverage (the
things prompt-wording alone could not), because it removes the underspecification
that made the model re-guess scope and resolution each run. The guidance is
defensively worded, so an empty scope contract is a no-op.

## The stack

```
litellm            → one chat-completion API across providers
instructor         → pydantic-native structured outputs + retry
keyring            → OS credential storage (Credential Manager / Keychain / Secret Service)
```

All pure-Python; wheels for every target OS; no native compilation.

## Module layout

```
src/latris/ai/
├── prompts.py          # 46 PromptSpecs: name, input schema, template, output hint
├── credentials.py      # env-var + keyring facade, key_in_env() context manager
├── config.py           # .graph-tooling/ai_config.yaml (committed)
├── context.py          # per-prompt context builders → ContextPack
├── proposals.py        # pydantic proposal schemas + apply() dispatchers
├── render.py           # proposal/result rendering
├── validate_urls.py    # URL sanity-checks on AI-proposed references
├── chains.py           # fixed prompt-chain definitions (CHAIN_LIBRARY)
├── chain_runner.py     # step-at-a-time chain session execution
├── interactions.py     # JSONL log append/read/approval
├── call.py             # end-to-end orchestrator (RESPONSE_MODELS dict, 46 entries)
└── adapters/
    ├── base.py         # ChatAdapter Protocol + ChatResult dataclass
    ├── mock_adapter.py # canned-response backend for tests and LATRIS_AI_MOCK=1
    ├── litellm_adapter.py  # real calls via instructor.from_litellm
    └── __init__.py     # get_adapter() picks mock or litellm from env
```

## Prompt chains

Beyond single-shot prompts, `chains.py` defines a small set of fixed
multi-step **prompt chains** (`CHAIN_LIBRARY` — e.g. `draft-model`,
`find-connections`) and `chain_runner.py` executes them one step at a
time. Each step is an ordinary `PromptSpec` call whose output feeds the
next; the runner holds a chain session so the GUI can drive a chain
step-by-step (preview/approve per step) rather than running the whole
sequence opaquely. Chains compose existing prompts — they add no new
mutation paths.

## Credentials story (GUI-compatible)

- **Env vars are the contract.** `litellm` natively reads `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, etc. Our adapter never sees a key directly.
- **Keyring is the helper.** `latris ai key set anthropic` stashes it
  in the OS credential store. `ai/credentials.py::key_in_env([...])` is a
  context manager that stages keyring values into env just for the call and
  cleans up after. The GUI imports these same functions — no CLI
  duplication.
- **Precedence:** per-call override > env var > keyring > `CredentialError`.
- **What never happens:** keys in argv (use `typer.prompt(hide_input=True)`);
  keys in repo files (`ai_config.yaml` has a `*_api_key`-substring ValidationError);
  keys in logs (`ai key list` prints provider + source, never values).

## Model resolution

Precedence (first match wins):
1. `--model <name>` flag on `ai call`
2. `LATRIS_AI_MODEL` env var
3. `.graph-tooling/ai_config.yaml` → `default_model`
4. Hardcoded default (`gemini/gemini-2.5-flash`)

The provider → credential-name mapping is inferred from the model string
(`claude*` → anthropic, `gpt*` → openai, …) and is overridable via
`LATRIS_AI_PROVIDER`.

Some providers mandate fixed sampling params: Moonshot fixes temperature
per model/mode — 1.0 with thinking enabled, 0.6 with the
thinking-disabled `extra_body` Latris sends (anything else is a hard 400).
`ai/config.py::PROVIDER_TEMPERATURE_OVERRIDES` forces those per provider,
applied after per-prompt and project-config resolution.

Moonshot's thinking models also reject the explicit `tool_choice` that
instructor's default TOOLS mode sends ("tool_choice 'specified' is
incompatible with thinking enabled"). The adapter routes moonshot models
through its JSON-mode instructor client — the same client Gemini uses —
so structured output works without tool calling.

Model comparisons across providers are recorded in the evaluations
archive (held in the private app repo) — see the Flash vs Kimi bake-off
for the current interim findings and the open arms.

## Call flow (what `ai call challenge <edge>` does)

```
require_project()
→ load ai_config.yaml
→ resolve_model()
→ build_context("ChallengeThisConnection", inputs, paths)
      # foundation + target + neighbours + existing challenges + past
      # interactions (tagged approved/rejected)
→ with key_in_env([provider]):
      adapter.chat(model, system, user, response_model=ChallengeProposal)
→ render the proposal for the human
→ confirm() → [y/N]
      yes → ChallengeProposal.apply(paths)  # → open_challenge → auto-commit
            → record_interaction(adoption="approved", tokens, cost)
       no → record_interaction(adoption="rejected", tokens, cost)
            (no substrate mutation)
```

The orchestrator never commits directly. Every mutation path goes through an
existing `operations/*` function that already owns the auto-commit contract.

## Proposal layer

Three proposal kinds for the first cut:

- **`ExplanationResult`** (read-only): `ExplainThisElement` returns prose;
  logged, never applied. No approval gate because there's nothing to
  approve — the log entry IS the deliverable.
- **`ChallengeProposal`** → `open_challenge(...)` + optional `add_turn(...)`.
  Carries an advisory `recommended_state`; the human picks the actual state
  via `latris challenge resolve` later.
- **`CitationsProposal`** → `add_reference(...)` for any `new_references`
  (existing bibkeys skipped), then `add_evidence(...)` for each
  `evidence_links` entry. **Hard safety rail:** refuses to apply any
  `evidence_links` whose bibkey is neither in the library nor in
  `new_references`. Tested (`tests/ai/test_call_flow.py::test_suggest_citations_refuses_fabricated_bibkey`).

## Context assembler

Each prompt has a bespoke builder in `context.py`. Goal: **relevant context,
not all context**. A big project's full state would blow the context window
and waste tokens.

| Prompt | What the builder injects |
|---|---|
| `ExplainThisElement` | foundation; target entity + neighbours (inbound/outbound edges); attributes on target; past interactions (approved/rejected tagged); assumptions + exclusions. |
| `ChallengeThisConnection` | foundation; target edge + endpoints; current attributes; existing challenges on same target (state annotated); past interactions; assumptions + exclusions. |
| `SuggestCitations` | foundation; target + attribute; **full reference library** (so AI can cite existing refs); existing evidence on this (target, attribute); scope exclusions. |

Every builder tags each past interaction with `[APPROVED BY HUMAN]`,
`[REJECTED BY HUMAN]`, or `[PENDING]` so rejected proposals appear as memory
but never as fact.

## Testing — mock spine

`LATRIS_AI_MOCK=1` swaps the adapter for `MockAdapter`. Tests pre-register
canned `ChatResult`s via `MockAdapter.shared().register_default(...)`.
No network, no keys, deterministic.

CI runs with mock mode enabled and the full suite stays green across
Win/Mac/Linux × py3.11/3.12.

## Trying a real call

```
latris ai key set anthropic
# prompts for key on stdin — never in argv

latris ai config show
latris ai config set default_model gemini/gemini-2.5-flash

latris ai call explain Price
latris ai call challenge <edge-id> --attribute polarity
latris ai call suggest-citations Price description
latris ai interactions list     # see the log + token usage
```

Every approved call produces one or more auto-commits (authored by you,
provenance `ai-proposed`), plus two audit-log commits for the interaction
record and its approval.

## What's been built since M10

All 46 prompts are now wired with response models and callable
end-to-end, organised into categories:

**Core prompts (original M8–M15 + GUI):**

| Prompt | Milestone | Scope | Intent |
|--------|-----------|-------|--------|
| `DraftConceptualModel` | M12 | model | action (multi-framing picker) |
| `AttackThisModel` | M12 | model | insight (read-only) |
| `ScopeCheck` | M12 | model | insight (read-only) |
| `FindNewConnections` | M12 | model | action (selective approval) |
| `RunElicitationInterview` | M14 | model | workflow (multi-turn) |
| `GeneratePack` | M15 | model | insight |
| `ProjectToFormalView` | GUI | model | insight |
| `SteelmanOpposingView` | GUI | element | action |
| `SyntheticPeerReview` | GUI | model | insight |
| `IdentifyResearchGaps` | GUI | model | insight |
| `ExplainThisElement` | M10 | element | insight (read-only) |
| `ChallengeThisConnection` | M10 | element | action |
| `SuggestCitations` | M10 | element | action |

**Reference prompts** (3): `ExpandBibliography` (action),
`CrossReferenceCheck` (insight), `SummarizeReference` (insight).

**Provenance-assist prompts** (4): `GenerateAssumptions`,
`SuggestDecisions`, `SuggestExclusions`, `RaiseQuestions` — suggest
provenance log entries from the current model state.

**Compose prompts** (4): `ExtractVariablesFromEvidence`,
`ExtractCausalClaims` — extract candidates from reference abstracts.
`SuggestVariables`, `SuggestConnections` — AI-synthesised suggestions
for the compose staging area.

**Interpret prompts** (10): `InterpretStructuralSummary`,
`InterpretKeyFindings`, `InterpretSensitivity`,
`InterpretAssumptions`, `InterpretEvidenceGaps`,
`InterpretEvidenceCoverage`, `InterpretAnswer`,
`InterpretImplications`, `InterpretConfidence`,
`InterpretOpenQuestions` — generate audience-targeted prose for each
interpretation section type.

**Configure prompt** (1): `SuggestEdgePolarities` — propose CLD/FCM
edge polarities or weights from evidence and model context.

**Interrogation / verification prompts** (Phase 3/4): `EdgeReclassify`
(action — propose a better edge kind), `ChallengeEdge` (action — open a
challenge against a connection), `EvidenceDemote` (action — flag
over-stated evidence for demotion), `VerifyClaimAgainstSource` (insight
— check a claim against its cited source), `CompletenessGate` (insight —
assess whether the model is complete enough to advance).

**Model-choice prompt** (1): `RecommendApproach` — recommend a modelling
formalism/approach as an auditable decision (Formalise phase).

**Provenance-fill prompt** (1): `FillProvenanceField` — draft a single
provenance-log field for user approval.

**Reference prompt** (1): `FindFoundationalReferences` — propose
foundational citations for the model's subject area.

**Evidence-gap prompt** (1): `ScanEvidenceGaps` — scan the model for
attributes lacking adequate evidence coverage.

**Story prompt** (1): `StoryBeatProse` — generate scrollytelling beat
prose for the Communicate-phase Story artifact.

**Note:** `ScopeCheck` checks both the modelling question *and* the
model boundary. The context builder feeds both into the prompt.

**GUI integration:** All 46 prompts are accessible through the AI panel
in the inspector. Mutation prompts use the two-step preview/approve
workflow (`AIProposalOverlay`). Read-only prompts display results in
`AIResultDisplay`. An `AIActivityLog` in the bottom third of the right
sidebar shows full interaction history with timestamps, costs, and
approval status.

## What's NOT yet built

- **Future boundary-related prompts:**
  - `ValidateBoundary` — suggest where the boundary is too vague or
    contradicts the exclusions list.
  - `SuggestBoundary` — propose a boundary from the modelling question.
  - `BoundaryImpact` — identify elements outside a proposed new boundary.
- Prompt caching (Anthropic `cache_control`) — cost optimisation for long
  system prompts; wire when a real user hits the bill.
- Streaming — not useful for structured outputs.
- Cost budgets / rate limits.
