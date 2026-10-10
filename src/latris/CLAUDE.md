# Python package — latris

## Layer discipline

`schema/` → `repo/` → `operations/` → `cli/` (strict dependency
direction — never import upward). `ai/` and `diff/` sit beside
operations. `exporters/` depends on schema + repo. `server/` is at
the same layer as `cli/` (both consume `operations/`).

## Five chokepoints

All access to these concerns goes through exactly one file:

- `repo/git.py` — every subprocess/git call
- `repo/yaml_io.py` — every YAML read/write (atomic via .tmp +
  os.replace; thread-safe via per-call YAML instances in server)
- `repo/layout.py` — every path, via the frozen `ProjectPaths`
  dataclass (~30 properties)
- `operations/commit.py` — every commit (`auto_commit`), plus
  batch grouping via `ContextVar`
- `schema/ids.py` — every ID (ULID-based, prefix-resolvable)

## Adding a new feature (end-to-end trace)

1. Pydantic model in `schema/` — with round-trip YAML test
2. Operation in `operations/` — returns `(model, commit_sha)`;
   ends with `auto_commit()`
3. CLI command in `cli/` — `@handle_cli_errors`; one parse + one
   call into operations + one print
4. Server route in `server/routes/` — pydantic request model,
   `Root` dependency injection, returns
   `{"result": model.model_dump(mode="json"), "commit_sha": sha}`
5. Test in `tests/` — `tmp_path` + `git_identity` fixture
6. Add to `worked_example/worked_example.py` (see root CLAUDE.md)

## Entity resolution

`operations/_resolve.py` resolves entities by: exact ID → label
(case-insensitive) → ID prefix (min 4 chars after `_`). Edges
resolve by ID or prefix only (no label lookup).

## Root parameter convention

Operations accept `root: Path | None = None`. CLI passes `None`
(discovers from cwd via `find_project_root()`). Server always
injects an explicit path via `Depends(get_project_root)`.

## Server (FastAPI + WebSocket)

- **App factory** in `server/app.py` — lifespan manages file
  watcher + WebSocket `ConnectionManager`.
- **Dependency injection** via `server/deps.py` — each route file
  defines `Root = Annotated[Path, Depends(get_project_root)]`.
- **Route pattern** — router with `/api/<domain>` prefix, pydantic
  request body, calls `operations/` directly, returns
  `{"result": ..., "commit_sha": ...}`.
- **State loader** in `server/state.py` — single dict of all
  project YAML/JSONL, served at `GET /api/state`.
- **File watcher** in `server/watch.py` — `watchfiles.awatch`,
  classifies changed paths into scopes, pushes
  `{"type": "state_changed", "scopes": [...]}` via WebSocket.
  Own-mutation suppression (2s window) prevents redundant pushes
  after server-initiated writes.

## Testing

Hermetic: `tmp_path` for filesystem isolation, `git_identity`
fixture sets `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env vars,
`LATRIS_AI_MOCK=1` stubs all LLM calls. No network, no
real API keys required. Test directory mirrors package layout.
Coverage reporting via `pytest-cov` (configured in `pyproject.toml`).
Full testing strategy in [`docs/engineering/TESTING.md`](../../docs/engineering/TESTING.md).
