# Telemetry implementation plan

Executable companion to `docs/engineering/AI_DIRECTIONS.md` (telemetry
chapter). 2026-11-25. Covers todos T1–T8 (which fold in U2 and U7). Grounded
in the 2026-11-25 tracking-surface audit of `Shannon-Bengtson/latris` and
latris-app.

## Decisions (2026-11-25)

1. **Separate telemetry service from day one.** A small standalone FastAPI
   service alongside graph_sync and session_broker in latris-app, with its
   own SQLite database — cost-neutral (same VM, same house pattern), and it
   keeps behavioural data out of the operational ACL database. The writer
   still sits behind a repository interface so Postgres/ClickHouse is a
   later swap, not a rewrite.
2. **CLI excluded for now.** The CLI emits no telemetry events (T3
   deferred). All v1 telemetry comes from the hosted surfaces: gui, mcp,
   server, broker. The `AIInteraction` extension (T2) still ships, because
   AI calls made through the app/MCP flow through the latris library inside
   containers.
3. **No third-party analytics.** Self-built only; the data stays ours.
4. **Privacy policy:** the user will update it before the first ingest
   deploys — tracked as a Phase 0 item, and it is a deploy blocker for
   Phase 2, not for Phases 0–1.
5. **Docs live in the repo.** This plan is `docs/engineering/TELEMETRY.md`;
   the directions doc is `docs/engineering/AI_DIRECTIONS.md`.
6. **Sequencing:** W3 (BN migration) merged as PR #8 on 2026-11-17 — no
   blocker. Remaining open work (sd/cld/dag/fcm migration, issue #3;
   app-side chart renderers, issue #5 / latris-app#3) is independent;
   telemetry Phases 1–2 can start immediately and run in parallel.

## Guiding constraints

1. One event envelope, one versioned payload registry, two tiers (local /
   hosted). New features register event types; the schema never churns.
2. The CLI is out of scope for v1 (decision 2). If CLI telemetry ever
   returns, it is local-only by default and uploads nothing without
   explicit per-user opt-in — that principle is permanent.
3. Hosted events are pseudonymous (`actor_ref` = HMAC of account id with a
   server-side salt), aggregate-first, and never store prompt text, model
   content, or project payloads — only metadata and outcome statistics.
4. latris's existing non-negotiables are untouched: no AI-authored commits,
   `apply()` as sole mutation path, closed prompt library.
5. House patterns to reuse: JSONL append via `yaml_io.dump_jsonl_append`;
   additive SQLite migrations via the `_ADDITIVE_COLUMNS` / `_migrate`
   pattern; pydantic-strict schema models; one service per concern with
   HTTP between them (graph_sync ↔ session_broker precedent).

## The event envelope

```
TelemetryEvent
  id            str          # new_id("evt")
  at            datetime     # UTC, client clock, server stamps receipt_ts
  surface       Literal["gui", "mcp", "server", "broker", "ci"]  # "cli" reserved, deferred
  event_type    str          # "ai.call.completed", "gui.feature", …
  type_version  int          # payload schema version for this event_type
  actor_ref     str | None   # pseudonymous; None for anonymous local use
  project_id    str | None   # latris project id; None for pre-project events
  session_id    str | None   # per-surface session (GUI tab, broker session)
  payload       dict         # validated against the registry entry
```

Payload registry: `EVENT_PAYLOADS: dict[tuple[str, int], type[BaseModel]]`
with `register_event_type(name, version, model)` — deliberately mirroring
`ai.registry.register_prompt`, so plugin authors (and future features) extend
telemetry the same way they extend prompts.

Initial event families (v1 payloads):

- `ai.call.completed` — prompt_name, model_id, latency_ms, tokens, cost,
  adoption, rejection_reason (opt), error_class; carries `interaction_id`.
- `ai.proposal.outcome` — interaction_id, outcome
  (survived-unedited / edited / reverted), window_days, computed by the
  sweeper (T6), not by clients.
- `gui.feature` — feature key (panel/prompt/chain step), action
  (opened/started/completed/abandoned), dwell_ms.
- `mcp.tool` — tool name, latency_ms, outcome class, client family if known.
- `session.lifecycle` — start/end, surface, duration, event count.
- `project.lifecycle` — created/saved/shared/archived (hosted tier only).
- `error.observed` — surface, error class, route context. No tracebacks with
  content; class + location only.
- (`cli.command` — specified but deferred with T3: command path, duration_ms,
  exit code class, latris version, formalisms touched. No arguments, no
  values.)

## Phase 0 — privacy groundwork (T8, doc half)

- [ ] Write the privacy stance page: what is collected per surface, opt-in
      wording for anything future-facing, retention (suggest: raw events 13
      months, aggregates indefinite), self-hoster story (their events stay
      in their deployment).
- [ ] Confirm the pseudonymisation scheme and where the salt lives (service
      env, not git).
- [ ] **User task:** update the privacy policy before the first ingest
      deploys (deploy blocker for Phase 2; Phases 0–1 unblock now).
- **Acceptance:** one page in the privacy doc + a config sketch; no code.

## Phase 1 — latris core: envelope + richer interactions (T1, T2; T3 deferred)

- [ ] `src/latris/schema/events.py` — `TelemetryEvent` + payload models +
      registry, with tests.
- [ ] `src/latris/telemetry/` — emitter with two backends: local JSONL
      (`.graph-tooling/telemetry.jsonl`, **gitignored**, not committed —
      behavioural data does not belong in shared project history) and HTTP
      POST to the telemetry service when configured (the in-container server
      path). No-op fast path when disabled.
- [ ] Extend `AIInteraction` (`src/latris/schema/ai.py`): add `at`
      (datetime, default now — the audit found the record has no timestamp),
      `surface`, `session_id`, `latency_ms`, and optional
      `rejection_reason` (taxonomy: wrong-fact / wrong-granularity /
      wrong-scope / style / other + free text). Additive change with
      defaults.
- [ ] Thread the new fields through `ai/interactions.py::record_interaction`
      and `ai/call.py::_finalize_call`; the confirm/reject path prompts
      (optionally, skippable) for a rejection reason.
- [ ] `latris ai interactions list` gains `--reason` display; no new read
      commands yet.
- [ ] ~~CLI instrumentation~~ — deferred (decision 2). The emitter's
      `surface="cli"` support lands with the envelope, but no typer wrapper
      ships in v1.
- **Acceptance:** full suite green; new tests for schema, emitter
      disabled/enabled and local/HTTP paths, rejection-reason capture, and
      that nothing is committed to git (test: telemetry file absent from
      `git status`).

## Phase 2 — hosted tier: the telemetry service + MCP middleware (T4)

- [ ] New service in latris-app (`src/latris_telemetry/`, mirroring the
      graph_sync/session_broker layout: `app.py`, `db.py`, `repository.py`,
      `config.py`, routes): own SQLite db with an `events` table `(id,
      receipt_ts, at, surface, event_type, type_version, actor_ref,
      project_id, session_id, payload_json)`, indexes on `(event_type, at)`,
      `(project_id, at)`, `(actor_ref, at)`, and the house `_migrate`
      pattern for additive columns. Deploy on the same VM.
- [ ] `POST /events` — batched ingest (array of envelopes), payload
      validation against the vendored registry version, actor
      pseudonymisation at the edge (account id → `actor_ref` before write),
      per-account rate cap reusing the `ai_call_counts` increment pattern.
- [ ] Broker/MCP middleware: wrap the MCP proxy path to emit `mcp.tool`
      (name, latency, outcome class) to the telemetry service — no tool code
      touched. Cheapest high-value instrument in the whole plan.
- [ ] Keep `ai_call_counts` for rate limiting; stop treating it as data.
- **Acceptance:** ingest round-trip test (authed call → row with
      pseudonymous actor, no email); middleware test emits one row per MCP
      call; load sanity (batch of 500 events). Deploy gated on the privacy
      policy update (Phase 0 user task).

## Phase 3 — GUI beacons (T5)

- [x] Relay route `POST /api/telemetry/events` on the latris server (the
      GUI's only backend): batch-accepts envelopes, stamps
      `surface="gui"`, validates payloads against the registry atomically
      (one bad payload 422s the batch), persists through the Phase 1
      emitter — local JSONL mirror primary, opted-in upload forwards the
      whole batch in one POST (bearer via `LATRIS_TELEMETRY_TOKEN`, an env
      var, never the committed config). Self-hosters' events stay in their
      own deployment; older backends 404, which is the GUI's silent-off cue.
- [ ] Small beacon module in the GUI: queue + flush every N seconds / on
      unload (`sendBeacon`), session id per tab, silently off when the
      server 404s (self-hosted/older backends).
- [ ] Instrument in priority order: AI panel (prompt run, proposal
      previewed / approved / edited-before-apply / rejected + reason picker),
      chain runner (step advance/abandon), checkpoints
      (answered/skipped/never-asked), feature opens (report, explorer,
      story, analyse), share-link toggles.
- [ ] The rejection-reason picker in `AIProposalOverlay` feeds both the
      local `AIInteraction` and the hosted event — one UX, two writes.
- **Acceptance:** e2e (the gui already has an e2e dir) covering one
      AI-approve flow and one chain-abandon flow asserting beacon payloads.

## Phase 4 — outcomes and read models (T6, T7)

- [ ] Outcome sweeper (in the telemetry service, scheduled): for each
      `ai.call.completed` with adoption=approved, walk the project's git
      history at +1d/+7d and classify the applied values (survived unedited
      / edited / reverted) — the mutation audit trail makes this computable
      today. Emit `ai.proposal.outcome` events.
- [ ] Nightly aggregate tables: adoption per (prompt, model), edit-after-
      approve rate, rejection-reason distribution, cost per adopted
      proposal, chain completion, funnel counts, MCP tool usage.
- [ ] Internal dashboard: start with a notebook or a single
      `/admin/metrics` page reading the aggregates; self-built, no third
      party (decision 3).
- **Acceptance:** sweeper replays a fixture repo with known edit history
      and classifies correctly; aggregates match hand-computed values on the
      fixture.

## Phase 5 — feeding the loops (connects to U-items)

- [ ] Per-project Loop A reads the interaction log and (where present) the
      local tier: stance injection (U3), disagreement map (U4), calibration
      curves (U5).
- [ ] Product-level: aggregates drive prompt-library changes and per-task
      model choice (U8); exemplar ranking for the library (L3) consumes
      "which models produce kept drafts" signals.
- [ ] Long-term harvests: approved-vs-rejected interaction pairs as
      contrastive data for few-shot selection or fine-tuning; VoI
      elicitation evaluation (U6) once checkpoint answers and sensitivity
      ranks are both in the stream.
- **Acceptance:** each U/L item's design doc cites the event types it
      consumes.

## Sequencing and effort

```
Phase 0 privacy groundwork — T8        (doc, ~1 session; user task: privacy policy)
Phase 1 latris core        — T1, T2    (small ×2; one PR-able branch; T3 deferred)
Phase 2 telemetry service  — T4        (medium; parallel with Phase 1; deploy gated on privacy policy)
Phase 3 GUI beacons        — T5        (medium; needs Phase 2 endpoint)
Phase 4 outcomes + read    — T6, T7    (medium ×2; needs real data; fixtures meanwhile)
Phase 5 loop integration   — U3–U8, L3 hooks   (ongoing)
```

Phases 1 and 2 run in parallel (different repos). Phase 4 can start against
fixtures before real traffic exists. Independent of the remaining legacy
formalism migration (#3) and the app-side chart renderers (#5).
