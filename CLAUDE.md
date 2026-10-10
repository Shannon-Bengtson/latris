# CLAUDE.md

Context for AI coding agents working in this repository.

## What this is

**Latris** — an evidence-native modelling workbench. This repo is the
open-source core: the `latris` Python package (`src/latris/`), its CLI,
and the FastAPI + WebSocket server backend. The Latris desktop app is
built on this package from a separate private repository.

Start at [README.md](./README.md) and [docs/README.md](./docs/README.md).

## Where things live

- [`src/latris/`](./src/latris/) — the package. Layered:
  `schema/` → `repo/` → `operations/` → `cli/`, plus `ai/` (LLM layer),
  `diff/` (semantic diffs), `exporters/` (DOT, Markdown, Word, HTML
  packs), `server/` (FastAPI + WebSocket backend), `sync/` (client for
  the collaboration control plane — the service itself is separate and
  proprietary; `sync.latris.app` is its public URL).
- [`tests/`](./tests/) — pytest suite mirroring the package layout.
  Hermetic — env-var git identity and `LATRIS_AI_MOCK=1`; no network or
  real keys required.
- [`worked_example/`](./worked_example/) — living worked example
  (acceptance test) and generated transcript.
- [`docs/`](./docs/) — engineering reference. Start at
  [docs/README.md](./docs/README.md).
- [`scripts/`](./scripts/) — `dev-server.sh` / `dev-stop.sh` (backend
  process lifecycle for dev), `bump-version.sh` (version + tag).

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
  `src/latris/server/help.py` (served at `/api/help/topics`). When you
  add, rename, or change a workflow phase, model type, or user-facing
  concept, update the relevant help topic body so documentation stays
  accurate.
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
See [docs/engineering/TESTING.md](./docs/engineering/TESTING.md).

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

Pushing a `v*` tag triggers `.github/workflows/publish.yml`, which
publishes the package to PyPI. Remind the user to push tags after a
bump; confirm version numbers with them rather than choosing
unilaterally.
