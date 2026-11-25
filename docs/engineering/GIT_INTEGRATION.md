# Git integration

## Principles

1. **Project = Git repo.** Every modelling project is a standalone git
   repository; collaboration is async via branches, commits, PRs, merges.
2. **Commits are behind the scenes.** The user does not type `git commit`.
   Every CLI mutation auto-commits with a generated semantic message.
   In the GUI, the user should not need Git vocabulary at all: Git is
   surfaced as versions, milestones, alternatives, compare, undo, and
   audit history.
3. **Human identity is enforced.** Git author is always the responsible
   human. AI authorship goes to `ai/interactions.jsonl` and provenance
   trailers — never the commit author field.
4. **Model-aware diffing.** Default diff and log commands interpret YAML
   changes semantically (`Edge A→B polarity flipped`) rather than as raw
   text. Layout files are excluded from semantic output.

## Identity guard

Before any commit, `operations/commit.py`:

1. Runs `git config user.name` and `git config user.email` (project-local
   first, then global).
2. Refuses if either is empty.
3. Refuses generic placeholders (`root`, `user`, `you@example.com`, `admin`).
4. On refusal, prints a per-OS hint for `git config --global`.

The `latris doctor` command runs this same check proactively.

## User-facing contract

Git is an implementation layer, not a prerequisite mental model. Technical
users may care that the project is a real repository and that history can
be inspected outside Latris. Non-technical users should not need to know
what a commit, branch, stage, or merge is during normal use.

The app should translate Git mechanics into modelling language:

| Git mechanic | Latris concept |
|---|---|
| Commit | Change in the timeline / undo point |
| Branch | Alternative model version |
| Tag or named checkpoint | Milestone |
| Diff | What changed in the model |
| Revert | Undo (and redo: a revert of the undo) — see ARCHITECTURE.md → "Undo / redo" |
| Pull/push | Sync with shared project location |

### Versions are not scenarios

A branch (alternative version) holds a different **structure or theory**: other
links, equations or framings. Options to compare (a policy, a delayed start, a
high-load world) are **scenarios**: value overlays saved in one version
(`views/parameters/sd-scenarios.yaml`), compared in one run on the same
sampled draws so their differences are paired. Putting options on branches
would break the pairing, force every model fix to be merged into each option,
and multiply branches (options × delays × worlds). Rule of thumb: change a
value → scenario; change the structure → version. A scenario can `extend`
another (a delayed option extends the undelayed one), and a comparison names
the reference each option is measured against.

Comparing versions means re-running the same analysis definitions on each
branch (results are recomputed from definitions, never copied) alongside the
semantic diff; a report renders one version at a pinned commit and includes
other versions only explicitly, each claim naming its version.

When Git errors occur, the product should explain the modelling consequence
first ("this project could not save a versioned change") and only then
show the underlying Git detail for users who can act on it.

## Commit message format

```
<verb> <what> [<qualifier>]

<optional body — human rationale from --message>

Provenance: human-authored | ai-proposed | ai-verified
Touched: substrate/conceptual.yaml, substrate/attributes/polarity.yaml
```

Examples:
- `Added node "Price" (type: variable)`
- `Added edge price→demand (kind: causal)`
- `Set polarity on edge price→demand: -`
- `Attached citation smith2023 to price→demand.description`
- `Resolved challenge 01HW... (state: modified)`

## `.gitattributes` and line endings

Committed at the repo root:

```
* text=auto eol=lf
*.yaml   text eol=lf
*.md     text eol=lf
*.jsonl  text eol=lf
```

Rationale: YAML and JSONL are text; diffs must be clean across OSes. LF is
the canonical on-disk form; Windows checkouts get CRLF via `core.autocrlf`
on user machines if they want, but stored content stays LF.

## `.gitignore` inside an initialised project

Created by `latris init`:

```
# generated outputs
reports/exports/

# layout (coordinates, colours) — excluded from semantic diffs by default
layout/*.layout.yaml
```

Layout files being git-ignored is a design commitment (see
[`ARCHITECTURE.md`](ARCHITECTURE.md) → "Repository layout"):
semantic work is versioned, visual work is not, to reduce merge friction.

## Semantic diff / log / status

`latris status`, `diff`, and `log` go through `diff/semantic.py`:

1. For the requested commit range (default: working tree vs HEAD), call
   `git diff --name-only` to find changed files.
2. For each changed file, load both sides via `yaml_io` into pydantic models.
3. Compute a structural diff: added entities, removed entities, attribute
   flips, edge direction changes, etc.
4. Format as a human-readable summary via `diff/semantic.py`.

Layout files and `reports/exports/` are skipped unless `--all` is passed.

## Future: AI authorship

When the LLM layer lands, every AI-originated change still commits as the
human who approved it. The AI's role is recorded in:

1. `ai/interactions.jsonl` — append-only record of prompt, proposal,
   approval decision, timestamp.
2. The commit trailer `Provenance: ai-proposed` or `ai-verified`.
3. The `proposed_by` informant on any attribute the AI touched.

No separate "AI author" in `git log` — that would lie about accountability.

## Remote collaboration

Latris projects are git repos, so collaboration = push/pull to a shared
remote. The Latris app routes this through the **Latris-native
control plane** plus an **invisible Gitea** git engine (deployed at
`https://sync.latris.app`), driven by the `sync` CLI group — not raw
GitHub auth. The control-plane service itself is a separate,
proprietary deployment; the open-source side ships the sync *client*
(`src/latris/sync/`). The earlier GitHub PAT / App / OAuth options
discussed here are superseded. The collaboration design doc and the
as-built deployment notes live in the private app repo.

### Collaboration model

Auth is the easy part. The harder question is what happens when two
people edit the same project concurrently:

- **Git merges** handle non-conflicting changes automatically (e.g. two
  people adding different nodes).
- **Conflicts** (e.g. both editing the same node's attributes) surface
  as git merge conflicts. The GUI needs to present these gracefully
  rather than dumping raw YAML conflict markers on the user.
- **Pull-before-push** discipline (or an auto-pull on open) reduces
  conflict frequency in practice.

This is where the real complexity lives — not in the auth.
