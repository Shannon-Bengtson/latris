# Contributing to Latris

Thanks for helping build Latris. This document is the short version; the
engineering docs under [`docs/engineering/`](docs/engineering/) are the
source of truth.

## Set up

```bash
git clone https://github.com/Shannon-Bengtson/latris.git
cd latris
python -m venv .venv
# Windows: .venv\Scripts\activate   —   mac/linux: source .venv/bin/activate
pip install -e ".[server,data,dev]"
```

Requires Python 3.11+ and git 2.40+ with a configured `user.name` /
`user.email`.

## Before you open a PR

1. **Tests pass**: `python -m pytest` (parallel by default).
2. **Lint clean**: `python -m ruff check src tests`.
3. **Worked example updated** if you added or changed any CLI command or
   user-facing feature: extend `worked_example/worked_example.py`, then
   regenerate the transcript with
   `pytest tests/test_worked_example.py --slow` and commit both. A
   feature that isn't in the worked example isn't done.

## Ground rules

- No business logic in `cli/` — a command is one parse + one call into
  `operations/` + one print.
- Respect the single chokepoints: `repo/git.py` (all subprocess),
  `repo/yaml_io.py` (all YAML), `repo/layout.py` (all paths),
  `operations/commit.py` (all commits), `schema/ids.py` (all IDs).
- No AI-authored commits; no secrets on disk (keys live in env vars or
  the OS keyring).
- The per-project state directory `.graph-tooling` is a frozen
  data-format constant — do not rename it.
- Layer discipline: `schema/` → `repo/` → `operations/` → `cli/`; never
  import upward. `server/` sits beside `cli/` and consumes
  `operations/`.

## Versioning

Never edit `src/latris/__init__.py` by hand — use
`bash scripts/bump-version.sh <version>` (bumps, commits, and tags;
pushing a `v*` tag triggers the PyPI publish workflow).

## License

By contributing you agree that your contributions are licensed under the
[Apache-2.0 license](LICENSE) that covers the project.
