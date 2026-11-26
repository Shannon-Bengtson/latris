# CLAUDE.md

Context for AI coding agents working in this repository.

## What this is

**Latris** — an evidence-native modelling workbench. This repo is the
open-source core: the `latris` Python package (`src/latris/`), its CLI,
and the FastAPI + WebSocket server backend. The Latris app (React, in the
browser at app.latris.app) is built on this package from a separate
private repository.

Start at [README.md](./README.md) and [docs/README.md](./docs/README.md).

## Where things live

- [`src/latris/`](./src/latris/) — the package. Layered:
  `schema/` → `repo/` → `operations/` → `cli/`, plus `ai/` (LLM layer),
  `diff/` (semantic diffs), `exporters/` (Markdown with a Mermaid
  sketch, DOT), `server/` (FastAPI + WebSocket backend), `sync/` (client for
  the collaboration control plane — the service itself is separate and
  proprietary; `sync.latris.app` is its public URL).
- [`src/latris/operations/formalisms/`](./src/latris/operations/formalisms/)
  — one plugin module per newer model type; adding a formalism is one
  module plus four central entries (ARCHITECTURE.md → "Adding a
  formalism"). What comes next is in
  [`docs/engineering/ROADMAP.md`](./docs/engineering/ROADMAP.md).
- [`tests/`](./tests/) — pytest suite mirroring the package layout.
  Hermetic — env-var git identity, commit signing off, and
  `LATRIS_AI_MOCK=1`; no network or real keys required.
- [`worked_example/`](./worked_example/) — living worked example
  (acceptance test) and generated transcript.
- [`docs/`](./docs/) — engineering reference. Start at
  [docs/README.md](./docs/README.md).
- [`scripts/`](./scripts/) — `dev-server.sh` / `dev-stop.sh` (backend
  process lifecycle for dev), `bump-version.sh` (version + tag),
  `health_report.py` (the weekly health check; see TESTING.md → "Weekly").

## Working principles

- **Design docs are source of truth.** Architectural commitments live in
  [`docs/engineering/`](./docs/engineering/): `ARCHITECTURE.md`
  (three-layer architecture), `SCHEMA_NOTES.md` (schema shape),
  `AI_LAYER.md` (AI contract), `GIT_INTEGRATION.md` (commit model),
  `TESTING.md` (test strategy). Don't drift from them silently; if you
  think one needs to change, propose it.
- **Schema before code-that-uses-schema.** New entities land as pydantic
  models with round-trip tests before any operation depends on them.
- **No business logic in `cli/`.** A CLI command is one parse + one call
  into `operations/` + one print. The server also imports
  `operations/` directly.
- **Single chokepoints.** Five files own their concern: `repo/git.py`
  (subprocess), `repo/yaml_io.py` (YAML), `repo/layout.py` (paths),
  `operations/commit.py` (commits), `schema/ids.py` (IDs).
- **No AI-authored commits.** Even AI-proposed mutations commit as the
  responsible human; AI involvement records to `ai/interactions.jsonl`
  and the commit's `Provenance:` trailer.
- **No secrets on disk.** API keys live only in env vars or OS keyring;
  `ai_config.yaml` is committed but rejects key-shaped fields
  defensively.
- **Keep help topics current.** User-facing help lives in
  `src/latris/server/help_topics/` — one Markdown file per topic, listed
  in `_order.txt`, loaded by `server/help.py` and served at
  `/api/help/topics`. When you add, rename, or change a workflow phase,
  model type, or user-facing concept, update the relevant topic's file so
  documentation stays accurate.
- **Commit after changes.** Commit work before finishing a session;
  don't leave modified or untracked work uncommitted.
- **Frozen constants.** The per-project state directory `.graph-tooling`
  and the keyring service name `latris-sync` are data-format constants —
  renaming them breaks existing users' projects/credentials. Never
  rename.

## Running tests

`python -m pytest` runs the suite in parallel by default (`-n auto`, via
`pytest-xdist`). For serial debugging — clean tracebacks, breakpoints,
deterministic output ordering — pass `-n0`. Targeted runs
(`pytest tests/ai/test_context.py`) are the inner-loop optimum.
[docs/engineering/TESTING.md](./docs/engineering/TESTING.md) has the layers, the guards (every route
tested, every command in the worked example — their gap lists only shrink), the coverage floor, and
**what "done" means** for a change. Follow it.

## Keep the notes current

This file, `src/latris/CLAUDE.md`, [`AGENTS.md`](./AGENTS.md) (for other agents, e.g. Kimi — it points
here rather than repeating this) and `docs/engineering/TESTING.md` are how the next agent learns this
repo. When a change makes one of them wrong, fix it in the same commit.

## Worked example is the acceptance test

Every new CLI command or user-facing feature must be added to
[`worked_example/worked_example.py`](./worked_example/worked_example.py).
After adding, run `pytest tests/test_worked_example.py --slow` to
regenerate
[`worked_example/worked_example_output.md`](./worked_example/worked_example_output.md).
Commit both the script change and the updated transcript. A feature that
isn't in the worked example isn't done. The transcript is living
documentation — it always shows the tool's full current capabilities.

## Versioning

`src/latris/__init__.py` (`__version__`) is the single version string,
read by hatchling. Never edit it by hand — use the bump script:

```bash
bash scripts/bump-version.sh 0.3.1        # bump + commit + tag
bash scripts/bump-version.sh 0.3.1 --no-tag  # bump + commit only
```

**Releasing (the normal way, from anywhere):** run the Publish workflow on
main with the new version — `gh workflow run publish.yml -f version=0.19.0`
(or Actions → Publish → Run workflow). It runs the bump script, pushes the
bump commit and the `v*` tag to main, and publishes to PyPI. Watch it with
`gh run watch`. Pushing a `v*` tag cut locally still publishes too. Either
way, confirm version numbers with the user rather than choosing
unilaterally.
