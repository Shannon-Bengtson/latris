# AGENTS.md

For any coding agent working here (Claude reads `CLAUDE.md` directly; Kimi and others start here).

**The guide is [`CLAUDE.md`](./CLAUDE.md)** — read it first, and `src/latris/CLAUDE.md` for the package.
This file doesn't repeat it, so the two can't disagree; it only adds what every agent must do.

## Before you call a change done

Follow **Done means** in [`docs/engineering/TESTING.md`](./docs/engineering/TESTING.md): tests at each
layer you touched, the worked example for a new command (transcript regenerated), the help topic for a
user-facing change, `python -m ruff check src tests` clean, `python -m pytest` passing. The guards fail
if a route has no test or a command isn't in the worked example; their gap lists only shrink — never add
to them.

## Keep the notes current

`CLAUDE.md`, `src/latris/CLAUDE.md`, `AGENTS.md` and `docs/engineering/TESTING.md` are how the next agent
learns how this repo works. When your change makes one of them wrong — a new guard, a moved file, a
changed rule — fix it in the same commit. If you find one already wrong, fix that too.

## House rules (from CLAUDE.md, the ones most often missed)

- Commit as the responsible human; record AI involvement in the `Provenance:` trailer, never as author.
- No secrets on disk. Never rename the frozen constants (`.graph-tooling`, `latris-sync`).
- Version bumps go through `scripts/bump-version.sh` — normally via the Publish workflow (`gh workflow run publish.yml -f version=X.Y.Z`), which also tags and publishes; confirm the number with the person first.
