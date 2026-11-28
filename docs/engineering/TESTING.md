# Testing

How latris is tested, what the guards enforce, and what "done" means for a change. Keep this file
current: when you add a guard, change a floor or a layer, update it in the same commit (see
[Keeping this current](#keeping-this-current)).

The Latris app (React, in the browser) is tested in the private app repo; its own guide is
`docs/engineering/TESTING.md` there. The two meet at the API: the app's types are generated from
latris's OpenAPI, so a schema change here shows up there as a type error.

## Layers

| Layer | Tool | What it proves | Where |
|-------|------|----------------|-------|
| **Schema** | pytest | Models round-trip through YAML; validation refuses what it should | `tests/schema/` |
| **Operations** | pytest | Each operation does the thing and commits it | `tests/operations/` |
| **Routes** | FastAPI TestClient | Each route, its request shape and its errors | `tests/server/` |
| **CLI** | typer CliRunner | Parsing, flags, error paths | `tests/cli/` |
| **Acceptance** | the worked example | The whole CLI, end to end, as a person would use it | `worked_example/`, `tests/test_worked_example.py --slow` |
| **Replications** | pytest + `latris replicate` | The engines reproduce textbook models' known results (published, closed form or exact), each expected value recomputed without Latris | `src/latris/replications/`, `tests/operations/test_replications.py` |
| **Guards** | pytest | The rules below hold across the codebase | named `*guard*`, `test_routes_are_tested.py`, `test_worked_example_coverage.py`, `test_formalisms.py`, `test_no_type_branches.py` |

## Hermetic

Every test runs without a network, real keys or global state: `git_identity` sets git's identity from
environment variables; commit signing is off for every test whatever the machine's git config says
(`tests/conftest.py` sets it through `GIT_CONFIG_*`, which reaches child processes too — a suite makes
thousands of throwaway commits, and a signing helper can run out of file handles under that load);
`LATRIS_AI_MOCK=1` swaps the LLM for a mock; each test builds its project in
`tmp_path`; the suite runs in parallel (`pytest-xdist`). The worked example writes its transcript outside
`tmp_path`, so it is `@pytest.mark.slow` and serialised.

## Guards

Guards are tests that check a rule across the codebase rather than one behaviour. When one fails it says
what to do.

| Guard | Rule |
|-------|------|
| `tests/server/test_routes_are_tested.py` | Every server route is named by some test. Only latris's own routes count: routes a plugin adds (`latris.server_plugins`) are tested where the plugin lives. |
| `tests/test_worked_example_coverage.py` | Every CLI command appears in the worked example. |
| `tests/operations/test_formalisms.py` | Every model type is complete: its plugin, spec field, analyses, foundations entry, help topic. |
| `tests/test_no_type_branches.py`, `tests/operations/test_no_type_branches.py` | Shared code doesn't branch on a model type's name (the first scans the whole package outside each type's own modules; the second the shared layers — operations, exporters, server, ai, diff — with a wider pattern). Both take the type ids from the registry. |
| `tests/operations/test_methods_register.py` | Every analysis names the method it stands on. |
| `tests/operations/test_workflow_declarations.py` | Every analysis and edit operation declares its step in the workflow structure (`schema/workflow.py`), and the classification is pinned. |
| `tests/test_places.py` | Every CLI command, server route and help topic declares its place in the workflow structure (`PLACE` in its module, `place:` in a topic's header); composites name what they carry out; the CLI reference's "Commands by stage and track" index is current (`python scripts/gen_cli_index.py`). |
| `tests/schema/test_model_types.py` | Model-type text is about the method, never the GUI's status. |
| `tests/test_complexity_guard.py` | No function is more complex than the limit (cyclomatic complexity 30, counted as `radon cc` counts it). |
| `tests/test_type_check_guard.py` | The type annotations are checked: `mypy` (settings in `pyproject.toml`, version pinned in the `dev` extra) finds no more errors in any file than it had. |

### Ratchets

Four guards started with existing gaps. Rather than fail from day one, each lists today's gaps in a file
that **only shrinks**:

- `tests/server/untested_routes.txt` — routes with no test yet. Empty since 2026-11-28: every route has a
  test, and the guard keeps it that way.
- `worked_example/not_in_worked_example.txt` — commands not in the worked example yet (some can't be:
  they need real keys or a network).
- `tests/complexity_exceptions.txt` — functions past the complexity limit, each with its score. A listed
  function must not grow; split it into smaller ones and take it off.
- `tests/type_errors.txt` — type errors per file. A file not listed has none; a listed file must not
  gain any, and when its errors are fixed its count comes down.

A new route, command, over-complex function or type error can't join a list: write the test, add the
command to the worked example, split the function, or fix the types. A listed one that is put right (or
removed) must come off — the guard fails until it does, so the list stays true.

The coverage floor works the same way: `fail_under` in `pyproject.toml` sits a point under measured
coverage and only goes up. When coverage rises, raise it.

Coverage is measured on the suite without the worked example, which runs in its own CI job. The CLI's
modules therefore read lower than they are tested: most of their commands run end to end there. A
command's own branches (its flags, its error messages) still want a test under `tests/cli/`.

## Done means

A change to latris is done when:

1. **Schema** changes have a round-trip test; **operations** a test in `tests/operations/`; **routes** a
   test in `tests/server/` (the route guard checks); **CLI commands** a step in the worked example (the
   coverage guard checks), with the transcript regenerated and committed. A new **command, route or help
   topic** declares its place in the workflow (the places guard checks).
2. A user-facing change updates its **help topic** (its file in `src/latris/server/help_topics/`).
3. `python -m ruff check src tests` is clean and the full suite passes (`python -m pytest`).
4. If the API changed, the app's types are regenerated there (`scripts/gen-api-types.sh` in the app repo)
   and the app typechecks.
5. This file and `CLAUDE.md` still describe how things work.

## Running

```bash
python -m pytest                                    # everything, in parallel
python -m pytest -n0                                # serial: clean tracebacks, breakpoints
python -m pytest tests/server/test_build_routes.py  # one file (the inner loop)
python -m pytest --cov --cov-report=term-missing    # with coverage (CI enforces the floor)
python -m pytest tests/test_worked_example.py --slow  # regenerate the worked-example transcript
python -m ruff check src tests                      # lint, as CI does
python -m mypy                                      # type-check (the guard runs it in the suite)
```

CI (`.github/workflows/ci.yml`) runs lint, the suite with coverage, and the worked example. A test that fails with a git
error (`GitError`: git can trip over itself on a busy runner) is run again, up to twice; any other failure
fails the first time, so a flaky test shows up instead of passing on a retry.

## Weekly

Two scheduled runs look at what a push doesn't:

- **Health check** (`.github/workflows/health.yml`, Monday morning in Australia): `scripts/health_report.py`
  runs the suite against today's releases of every dependency (with coverage, and the ten least-covered
  files, so the trend shows), audits the dependencies for known
  vulnerabilities (pip-audit), and measures risky patterns (bandit), complexity and maintainability
  (radon), size, dead code (vulture), duplication (jscpd), lint beyond the project's rules, and the length
  of each ratchet list. The report is the run's summary page, kept as an artifact for 90 days. It fails
  only on a known vulnerability or a failing test; then it opens an issue labelled `health-check` (or
  comments on the open one) and closes it when a run passes. Try it locally with
  `python scripts/health_report.py --src src/latris --skip-tests` (the tools are listed in the workflow).
- **The full matrix**: CI (`ci.yml`) runs on all three operating systems and both Python versions on the
  same morning, which pushes don't.

Scheduled runs start from the default branch, and GitHub pauses them in a repository with no activity for
60 days; re-enable them from the Actions tab.

## Keeping this current

This file is read by every agent that works here (Claude via `CLAUDE.md`, others via `AGENTS.md`). When
you add a guard or a test layer, change a floor, or change what "done" means, update this file in the
same commit. If you find it wrong, fix it — a stale testing guide is worse than none.
