# Latris

**Structure for defensible reasoning.**

Latris is an evidence-native modelling workbench for building defensible
causal and systems models — structured provenance, challenge workflows,
git-native versioning, AI-assisted drafting under human approval, and
report generation.

This repository is the open-source core: the Python package (`latris`),
its CLI, and the FastAPI + WebSocket server backend. The Latris desktop
app (React + Electron) is built on top of this package from a separate
private repository.

**New here?** The Latris product — a desktop app for modellers and for
the people who must weigh in on their models — lives at
[latris.app](https://latris.app) (invite-only early access). This
repository is the open backend that powers it.

- Every modelling project is a **git repo** — every change is an
  inspectable, reversible commit.
- Evidence and provenance are **first-class data**, not annotations:
  citations, assumptions, decisions, challenges, sign-offs.
- AI assistance returns **structured proposals**, never free-form
  mutations; a human approves before anything commits.
- One substrate, many formalisms: qualitative CLD/DAG views today, a
  built-in discrete **Bayesian Network engine** (state spaces, CPTs with
  per-cell provenance, exact inference, parameter learning), and more
  views on the architecture's path.

Status: **alpha** (0.3.1). Apache-2.0 licensed.

## Prerequisites

- **Python 3.11+** on PATH
- **git 2.40+** on PATH, with `user.name` and `user.email` configured
  globally (Latris commits as you, and enforces that identity)

## Install

From PyPI:

```bash
pip install "latris[server,data]"
latris --version
latris doctor          # verify git + identity
```

From source:

```bash
git clone https://github.com/Shannon-Bengtson/latris.git
cd latris
python -m venv .venv
# Windows: .venv\Scripts\activate   —   mac/linux: source .venv/bin/activate
pip install -e ".[server,data,dev]"
latris doctor
```

Optional extras:

| Extra | Brings in | For |
|-------|-----------|-----|
| `server` | FastAPI, uvicorn, pandas, scipy, pgmpy | The API server (`python -m latris.server`) |
| `data` | pandas, scipy | Dataset wrangling and statistics |
| `quant` | pgmpy | Quantitative inference (also in `server`) |
| `dev` | pytest, xdist, ruff, build | Running the test suite |

## Quickstart

```bash
# 1. Create a project (a git repo with the full model structure)
latris init air-quality --question "What drives urban air quality?"

cd air-quality

# 2. Build a model: nodes, then edges
latris node add "Traffic volume" --kind variable
latris node add "NO2 concentration" --kind variable
latris edge add <traffic-id> <no2-id> --kind causal

# 3. Inspect — every step above was a git commit
latris status
latris log

# 4. Export
latris export md --output reports/report.md
latris export dot --view cld --output reports/model.dot
```

The full command catalogue is in
[`docs/engineering/CLI_REFERENCE.md`](docs/engineering/CLI_REFERENCE.md).

## Run the API server

```bash
python -m latris.server --project-root ./air-quality
```

Serves the full CRUD/AI/export API on **http://127.0.0.1:8741** (the
same backend the Latris desktop app embeds). `--help` lists flags.

## AI layer (bring your own key — or your own agent)

AI calls go through a vendor-agnostic adapter (litellm + instructor);
secrets live in your OS keyring, never on disk:

```bash
latris ai key set anthropic      # or openai / gemini / groq / ...
latris ai config show            # default model lives in .graph-tooling/ai_config.yaml
```

Set `LATRIS_AI_MOCK=1` to stub all AI calls (used by the test suite and
CI; the pre-rename `GRAPH_TOOLING_AI_MOCK` is still honoured for one
release).

Working from an agent (Claude Code, Kimi, …) with no API key?
`latris ai task emit <prompt> --inputs '<json>'` produces a self-contained
task package your agent can answer; `latris ai task apply --task task.json
--from response.json` ingests the answer through the same human-approval
pipeline (recorded as `external-agent`). See
[docs/engineering/AI_LAYER.md](docs/engineering/AI_LAYER.md).

## Tests

```bash
python -m pytest              # full suite, parallel via pytest-xdist
python -m pytest -n0          # serial, for clean tracebacks
python -m pytest tests/test_worked_example.py --slow   # acceptance test (regenerates the transcript)
```

## Documentation

- [`docs/README.md`](docs/README.md) — documentation index
- [`docs/engineering/ARCHITECTURE.md`](docs/engineering/ARCHITECTURE.md) — how it's built
- [`docs/engineering/CLI_REFERENCE.md`](docs/engineering/CLI_REFERENCE.md) — command catalogue
- [`worked_example/worked_example_output.md`](worked_example/worked_example_output.md) — a full end-to-end session transcript
- [`llms.txt`](llms.txt) — machine-readable doc map for AI agents

## License

[Apache-2.0](LICENSE) — Copyright (c) 2026 Shannon Bengtson.

---

## For AI agents

**Latris** is an evidence-native causal-modelling CLI + API server. The
engineering docs are the source of truth for an agent working in a
Latris project: start from [`llms.txt`](llms.txt) and
[`docs/README.md`](docs/README.md).

**An agent can act as the model.** The AI layer doesn't require its own
API key: any of the 46 AI prompts can be delegated to whichever agent is
already in the loop via
`latris ai task emit <PromptName> --inputs '<json>'`, which writes a
task package (prompt + project context + response schema). The agent
answers it as JSON, then a human runs
`latris ai task apply --task task.json --from response.json`. Same
approval gates apply; the interaction is recorded as `external-agent`.
See [AI_LAYER.md](docs/engineering/AI_LAYER.md) § "Delegated calls".

**What's available varies by model type.** `latris capabilities` (or
`latris capabilities --json`) lists every registered model type with
`can_use_today: true/false`. Only `cld`, `dag`, `bn`, `fcm`, and `sd` are
stable/switchable today; the rest (`theory_of_change`, `gsn`, and
13 others) are registered but not yet switchable. Each entry's `roadmap`
field says where it stands: fault tree, event tree, bow-tie, GSN and
theory of change are `roadmap`; a few are `parked`; the rest are
`not_planned` — registered, but not something to describe as coming — `latris view project
<kind>` raises a `ValueError` if `kind` isn't stable. A few categories
(black-box ML) are excluded by design, not "not yet." Checking this
first avoids claiming Latris can build a model type that isn't actually
usable yet.

**Moving a project online so a human can see it in a browser.** When
viewing or sharing the model at `https://app.latris.app` would help,
rather than reading terminal output, the path is: `latris sync login
--email <their email>` (sends a one-time code that the human relays
back, then re-run with `--code`), then
`latris sync share "<project name>"`, which prints the exact link to
open. No desktop install needed.

Setup (one shot):

```bash
pip install "latris[server,data]"
```

Minimal working session (init → node → edge → export → history):

```bash
latris init demo --question "Does X cause Y in context Z?"
cd demo
latris node add "X" --kind variable
latris node add "Y" --kind variable
latris edge add <x-id> <y-id> --kind causal   # IDs from the node add output
latris export md --output reports/report.md
latris log                                     # every mutation is a git commit
```

The complete, always-current demonstration of every command is the
worked example:
[`worked_example/worked_example_output.md`](worked_example/worked_example_output.md)
(generated by `worked_example/worked_example.py`; the generator is the
repo's acceptance test). It answers most questions about how the tool
behaves without needing to ask the user. After changing CLI behaviour,
regenerate it (`pytest tests/test_worked_example.py --slow`) and commit
the updated transcript.

Hard rules when modifying this repo: no business logic in `cli/` (one
parse + one call into `operations/` + one print); respect the five
chokepoints (`repo/git.py`, `repo/yaml_io.py`, `repo/layout.py`,
`operations/commit.py`, `schema/ids.py`); no AI-authored commits; no
secrets on disk. See [`CLAUDE.md`](CLAUDE.md) and
[`src/latris/CLAUDE.md`](src/latris/CLAUDE.md).
