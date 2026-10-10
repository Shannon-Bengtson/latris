# Testing Strategy

## Current counts (2026-07, post repo-split)

- **~1,850 Python tests** collected by `python -m pytest --collect-only -q`
- CI matrix: `{ubuntu, macos, windows} × {3.11, 3.12}` on manual
  `workflow_dispatch`; slim single-job matrix on push/PR
- The desktop GUI (React + Electron) is developed in the separate private
  app repo and carries its own Vitest/Playwright suites there.

## Four test layers

| Layer | Tool | What it tests | Where |
|-------|------|---------------|-------|
| **Unit** | pytest | Individual functions, helpers | `tests/` |
| **Integration** | FastAPI TestClient | Server routes + operations together | `tests/server/`, `tests/integration/` |
| **CLI smoke** | typer.testing.CliRunner | CLI error paths, flags, outside-project guards | `tests/cli/` |
| **Acceptance** | Worked example script | Full CLI workflow end-to-end | `worked_example/` |

## Hermetic test contract

All tests run without network access, real API keys, or global state:

- **Git identity**: `conftest.py` injects `GIT_AUTHOR_*` / `GIT_COMMITTER_*`
  env vars via the `git_identity` fixture. Tests never touch `~/.gitconfig`.
- **AI mocking**: `LATRIS_AI_MOCK=1` activates `MockAdapter`, which
  returns canned responses. No LLM API calls leave the machine.
- **Filesystem isolation**: Every test uses `tmp_path` for its project
  directory. No shared state between tests.
- **Parallel-safe**: Full-suite invocation runs under `pytest-xdist`
  (`-n auto`). Each worker is a separate process, so env-var injection
  and `tmp_path` survive cleanly. The one non-hermetic test
  (`tests/test_worked_example.py`, gated by `@pytest.mark.slow` and
  writing the transcript outside `tmp_path`) carries
  `@pytest.mark.xdist_group("serial")` to prevent races.

## Coverage

- **Python**: `pytest-cov` configured in `pyproject.toml`. Run explicitly
  with `python -m pytest --cov --cov-report=term-missing`.
- **CI**: The suite runs in `.github/workflows/ci.yml`. Coverage is
  collected on Ubuntu + Python 3.12 only.
- **Targets**: Track from day one. Do not enforce `fail_under` until
  baselines are established.

## What NOT to test

- Pure display components that just render children (cover with E2E later)
- External library behavior (pydantic validation, git internals)
- Code that is purely generated or configuration
- One-line re-exports or `__init__.py` barrel files

## Adding tests for a new feature

Follow the six-step trace in `src/latris/CLAUDE.md`:

1. **Schema model** → round-trip test in `tests/schema/`
2. **Operation** → unit test in `tests/operations/` with `project` fixture
3. **CLI command** → covered by worked example (add step to
   `worked_example/worked_example.py`)
4. **Server route** → test in `tests/server/` with `client` fixture
5. **Worked example** → run `pytest tests/test_worked_example.py --slow` and
   commit the updated transcript

## Running tests

```bash
# Python quick/default (parallel via pytest-xdist)
python -m pytest

# Serial run (cleaner tracebacks for debugging)
python -m pytest -n0

# Python coverage
python -m pytest -n auto --cov --cov-report=term-missing

# Worked-example acceptance test (regenerates the transcript)
python -m pytest tests/test_worked_example.py --slow

# Single Python test file
python -m pytest tests/ai/test_context.py -v
```

## Known test/CI debt

- **Python coverage threshold remains at 74.** The Story test debt is paid
  (`server/routes/story.py` is fully covered), but real total coverage is ~76%;
  the historical **78** was aspirational and never actually enforced (the CI
  coverage gate had not run). Climbing to a real 78 needs broad tests across
  thin server routes (`interpret`, `sync`, `references`, `findings`, `watch`)
  and is tracked as a separate push. See `pyproject.toml`
  `[tool.coverage.report]`.
