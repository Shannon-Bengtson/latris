# Latris

**Structure for defensible reasoning.**

Latris is an evidence-native modelling workbench for building defensible
causal and systems models — structured provenance, challenge workflows,
git-native versioning, AI-assisted drafting under human approval, and
report generation.

This repository is the open-source core: the Python package (`latris`),
its CLI, and the FastAPI + WebSocket server backend. The Latris app
(React, running in the browser at app.latris.app) is built on top of this
package from a separate private repository.

**New here?** The Latris product — a browser app for modellers and for
the people who must weigh in on their models — lives at
[latris.app](https://latris.app) (open sign-up at
[app.latris.app](https://app.latris.app)). This repository is the open
backend that powers it.

| | Open-source library (`pip install "latris[data,quant]"`) | Latris app ([app.latris.app](https://app.latris.app) — free account, nothing to install) |
|---|---|---|
| What it is | The engine and CLI: every analysis, a Markdown report with a Mermaid sketch, `latris link` | The hosted **interactive report** (typeset figure, result charts, interpretation — what a board reads), the visual editor, Word reports, review packs reviewers fill in, the scrollytelling story, saved models with short links |

A `latris link` link **is** the shareable report: it opens the interactive
report in the app. Send it as it is — no wrapper page or separate document.

- Every modelling project is a **git repo** — every change is an
  inspectable, reversible commit.
- Evidence and provenance are **first-class data**, not annotations:
  citations, assumptions, decisions, challenges, sign-offs.
- AI assistance returns **structured proposals**, never free-form
  mutations; a human approves before anything commits.
- One substrate, many formalisms: causal loop diagrams and DAGs; fuzzy
  cognitive maps; a discrete **Bayesian network** engine (per-cell
  provenance, exact inference with hard and soft evidence, the most likely
  explanation, learning from data, sensitivity and Monte Carlo over the
  tables); and **system dynamics** (unit-checked equations, delays,
  scenarios, Monte Carlo bands, sensitivity and loop dominance). A causal
  loop diagram and an SD model can share one project: its loops include
  feedback through stocks.

Status: **alpha**. Apache-2.0 licensed.

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
same backend the Latris app embeds). `--help` lists flags.

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

**Latris** is an evidence-native causal-modelling CLI + API server. This
section ships with the package: `latris docs` prints it with no network
(`latris docs readme` for the whole README, `latris docs llms` for
[`llms.txt`](llms.txt)), and `latris capabilities` lists what Latris can
do. The engineering docs are in the repo:
[`docs/README.md`](docs/README.md).

**Install with the extras:** `pip install "latris[data,quant]"` (SD
integration methods and Bayesian inference need them; `latris capabilities
--json` shows what's installed).

**What you get where** — so you hand a person the right thing:

| | Open-source library (`pip install "latris[data,quant]"`) | Latris app ([app.latris.app](https://app.latris.app) — free account, nothing to install) |
|---|---|---|
| What it is | The engine and CLI: every analysis, a Markdown report with a Mermaid sketch, `latris link` | The hosted **interactive report** (typeset figure, result charts, interpretation — what a board reads), the visual editor, Word reports, review packs reviewers fill in, the scrollytelling story, saved models with short links |

A `latris link` link **is** the shareable report: it opens the interactive
report in the app. Send it as it is — no wrapper page or separate document.

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
`latris sync share "<project name>"`, which pushes the project and
prints where to open it (the human signs in at that address and picks
the project from their list). No desktop install needed.

Setup (one shot):

```bash
pip install "latris[server,data]"
```

**Ask before you build.** Latris records the situation a model is built
in and puts it at the top of the report, but only if someone asks for it.
Unless the request already says, ask the person, in one message of at most
three short questions: the background (what's happening, and what decision
this informs), who will read it, and what they expect the answer to be. Add
anything they share as sources. If they'd rather you just build, do, and
record each unanswered point with `latris question add` or `latris
assumption add`, so the gap shows in the report instead of disappearing.

**Choosing a model type.** People rarely know which formalism fits their
question — guide the choice by the kind of answer needed, and record the
reasoning with `latris project select-models` so the report's modelling
approach shows it:

- "How does this work — what feeds back on what?" → `cld`. Start here by
  default: the cheapest honest answer, and every other formalism builds
  on it.
- "Can this effect actually be estimated, and from what data?" → `dag`.
  Identification only — adjustment sets and d-separation, no effect
  sizes, no counterfactuals.
- "How likely is each outcome, and what would change my mind?" → `bn`.
  Discrete states and probabilities; CPTs elicited, learned, or mixed.
- "Which forces dominate, roughly?" → `fcm`. Signed, weighted links and
  steady-state tendencies — not year-three numbers.
- "How will it behave over time if we intervene?" → `sd`. Stocks, flows,
  units, scenarios — the most commitment; build the CLD first.

The same substrate carries across: factors, links, evidence and
challenges all stay, and quantifying a CLD as FCM/BN/SD later never means
redrawing. More than one formalism can be right — triangulating (say, a
CLD plus a DAG on the same substrate) is a strength, not a mistake. The
human-facing version of this guide lives at
<https://latris.app/formalisms/>.

A causal loop diagram, end to end (works in a sandbox with no API key):

```bash
# Every change is a git commit, so git needs an identity first.
git config --global user.name "Your Name"; git config --global user.email "you@example.com"
# You're an AI agent: record what you create as AI-proposed, not as the person's own work.
export LATRIS_DEFAULT_ORIGIN=ai-proposed

latris init volunteers --question "Why are volunteers leaving?"
cd volunteers
latris project select-models cld

# Fastest: the whole model in one file, one command, one commit (YAML or JSON;
# '-' reads stdin). Checked in full first — a typo changes nothing.
latris build --spec model.yaml
#   context:                             # top of the report: the situation, for whom, the person's own prior
#     background: "Food bank lost a third of its volunteers since 2023; the board decides on a paid coordinator."
#     audience: "The food bank's board"
#     boundary: "Current volunteers only; recruitment is out of scope."
#     intuition: "Rostering changes after the merger pushed people out."   # what they expect, in their words
#   outcome: Volunteer departures        # what the model explains
#   factors:
#     - {label: Workload, description: Hours asked of each volunteer.}
#     - {label: Burnout}
#     - {label: Volunteer departures}
#   links:
#     - {from: Workload, to: Burnout, polarity: "+", reason: "More hours, more exhaustion.",
#        confidence: high, sources: [smith2021], contradicts: [tuohy2015]}
#   sources:
#     - {key: smith2021, title: Volunteer burnout, authors: ["Smith, J"], year: 2021,
#        url: "https://doi.org/...", extract: "Abstract: ..."}   # extract: the text you actually read
#     - {key: tuohy2015, title: Workload and retention revisited, year: 2015}
#   assumptions:
#     - {text: "Service demand stays steady as numbers fall.", target: "Burnout -> Volunteer departures",
#        rationale: "Demand data only covers 2019-2023."}
#   questions: ["Does recognition matter independently of workload?"]
#   decisions: [{statement: "Left out paid staff.", rationale: "The program has none."}]
#   findings:                            # recorded as proposed; a person approves them
#     - {statement: "Workload drives departures through burnout.", category: dynamics,
#        targets: ["Workload -> Burnout"]}
#   challenges: [{argument: "Burnout may follow intent to leave.", target: "Burnout"}]
#   interpretation:                      # prose for report sections
#     - {section: answer_to_question, prose: "Volunteers leave mainly because...", by: ai}

# Or one change at a time:
latris project set background "Food bank lost a third of its volunteers since 2023."
latris project set audience "The food bank's board"
latris project set predictions "Rostering changes pushed people out."   # their prior, in their words
latris node add "Workload" --kind variable
latris node add "Burnout" --kind state
latris attr set "Workload" description "Hours asked of each volunteer."
latris edge add "Workload" "Burnout"            # nodes by label; prints the edge id
latris view set cld <edge-id> polarity + --rationale "More hours, more exhaustion."
#   re-running view set replaces the value and the rationale
#   negative numbers need `--`:  latris view set fcm <edge-id> weight -- -0.4

latris ref add smith2021 --title "Volunteer burnout" --author "Smith, J" --year 2021
latris ref snapshot smith2021 --url "https://..." --extract "Abstract: ..."   # what you read
latris ref add jones2019 --title "..." --cited-via smith2021   # read only as described in smith2021
latris evidence add <edge-id> polarity smith2021 --verified-by ai
latris evidence add <edge-id> polarity tuohy2015 --verified-by ai --contradicts   # a source against the link
latris evidence check "Workload -> Burnout" polarity smith2021 supports --by ai \
  --rationale "Hours predicted exhaustion." --quote "hours predicted emotional exhaustion"   # copied, not paraphrased
latris ref edit smith2021 --doi 10.1234/abcd     # correct a source (also --title, --url, ...; "" clears)
latris ref remove tuohy2015 --with-citations     # drop a source and its citations
latris evidence remove "Workload -> Burnout" polarity smith2021   # detach one citation
latris assumption add "Service demand stays steady as numbers fall."  # for unsourced links
latris view role cld "Volunteer departures" outcome   # the outcome isn't suggested as an intervention point

latris check coherence                           # wording vs. polarity contradictions
latris analyse loops                             # reinforcing / balancing loops
latris finding add "Overload is a reinforcing loop." --category structure --target "Workload"

latris interpret initialise                      # board-facing sections, built from the model
latris interpret show answer_to_question         # the claims this section must stand on
latris interpret set-prose answer_to_question "..." --by ai   # write it (or generate-prose with a key)

latris export md --pack client --no-ai -o report.md   # report with a Mermaid diagram
latris link                                      # a link that opens it in the Latris app — give it to the person
latris log                                       # the full history
```

Choosing a report — pick the pack for whoever will read it
(`latris capabilities` lists these too):

| Pack | For | What's in it |
|---|---|---|
| `client` | a client, board or funder | **answer first**: the interpretation (answer, implications, confidence, then the rest), the diagram with its loops, approved findings, then each link with its reason and evidence, and sources — no internal IDs, no change log |
| `publication` | a paper or public write-up | as `client`, with full references |
| `review` | a reviewer checking the model | evidence, open challenges and questions, findings |
| `workshop` | a stakeholder session | structure, assumptions, open questions, session notes |
| `audit` | an auditor / the modelling team | everything, including decisions, sign-offs and data |

The board-ready part is the interpretation: fill its sections (above)
before exporting a `client` report, or the report is just the evidence
base. Word, review-pack and scrollytelling-story versions, and a hosted
report link to share, are made in the Latris app (app.latris.app).

Tips for agents:

- **`latris --json <command>`** prints one JSON object (`{"result", "commit_sha"}`)
  for node, edge, attr, view set, ref, evidence, finding, challenge, project
  show, check, analyse, interpret, bn, sd, fcm and results commands — no
  output parsing needed.
- **One model, several views.** `latris project select-models cld fcm` (or
  `bn`, `dag`) keeps the same factors and links and adds a quantitative view —
  set FCM weights or BN probability tables on the diagram you already have
  instead of starting again.
- **Quantified answers carry their evidence.** For system dynamics: save
  what-ifs (`latris sd set-scenario "Low emissions" --set "Emission Rate=80"`)
  and compare them (`sd simulate --scenario ...`); give uncertain values a
  range (`sd set-uncertainty "Emission Rate" triangular --min 90 --mode 120
  --max 140 --reason "..."`), then `sd monte-carlo` (how sure: bands),
  `sd sensitivity <variable>` (which values matter, flagging unreviewed ones)
  and `sd loops` (which feedback loop drives it). These and `bn query` are
  recorded: the client report's Results section shows the latest of each,
  and `latris interpret refresh-claims` turns them into claims the
  interpretation can use. `latris results list` / `results hide <run>`
  choose what the report shows. Values you set are AI-proposed under
  `LATRIS_DEFAULT_ORIGIN=ai-proposed`; the report says so. For Bayesian
  networks: `bn query -s "Heavy Rain=yes:0.8"` (soft evidence: 80% sure),
  `bn explain -e "Road Closed=yes"` (the most likely combination of causes),
  and `bn set-uncertainty Flood --n 10` + `bn monte-carlo Flood` (how sure
  the probability is when the tables are estimates) — all recorded.
- **No API key?** Checks and drafting that use AI (e.g. the completeness check)
  can be answered by you: `latris ai task emit <PromptName> --inputs '<json>'`,
  then `latris ai task apply` (see "An agent can act as the model" above).
  `export md --no-ai` (and any export without a key) skips the AI prose.
- **Evidence you attach is marked AI-proposed and unverified** until a person
  reviews it — say so when you hand the model over. Attaching a citation
  says only that it was attached; whether the source actually supports the
  claim is recorded with `latris evidence check "<from> -> <to>" polarity
  <key> supports|against|off-topic --rationale "..."` (a person by default;
  an agent that read the source adds `--by ai`). Links can be named
  `"From -> To"` wherever a command takes one.
- **A quote must be copied, not paraphrased.** An agent's `supports` needs
  `--quote`, and the quote is looked up in the text Latris holds for the
  source: the `extract` you saved (`ref snapshot`, or `extract:` in a build
  spec), a fetched full text (`ref fetch`) or the abstract. Whitespace,
  quote marks and case don't matter and `...` marks a gap; a quote that
  isn't there is refused. So save the passage you read first. The report
  says what each check rests on — an extract of the full text, or only the
  abstract or a summary — so a check against an abstract never reads as a
  check against the paper.
- **Sources that disagree with a link go on that link** with `--contradicts`
  (or `contradicts:` in a build spec) — not as a challenge and not left
  uncited. The report then shows the link's sources for and against under
  "Contested links", and the confidence and open-questions claims name it.
  Like any citation it is not yet checked: check it with `evidence check
  ... against` once you've read it.
- **Only give identifiers you have seen.** A DOI recalled from memory is
  worse than none (`ref add` refuses what isn't shaped like a DOI, but can't
  tell a real one from a wrong one). A study you only read about in another
  source (a review) takes `--cited-via <that source's key>` (`cited_via:` in
  a build spec); the report says it was read second-hand.
- **Correct the record with commands, never by editing the YAML.** `ref edit`,
  `ref remove`, `evidence remove` (and `evidence check ... unchecked` to undo
  a check) are recorded changes with reasons; a hand edit committed with git
  skips the model's history.
- **Links that are true by definition** (departures reduce the number of
  volunteers) take `confidence: by-definition` (or `latris attr set <link>
  confidence by-definition`). They need no source: they don't count against
  coverage, and the figure draws them solid rather than as unproven.
- **Findings you add are proposed.** The client report lists only approved
  ones (it says how many are waiting); a person approves each with
  `latris mature approve <finding-id>`.
- **`latris ai task apply` stops for a person's y/N** before it changes the
  model — by design. Leave the task and response files for them; results
  (e.g. completeness) reach the report only after they apply it.
- **For a person, give them the client report** (`--pack client`) with the
  interpretation sections written — that's the board-ready version. It has the
  diagram, each link's reason, the evidence and the sources, without internal IDs.
- **Before handing over, run `latris check handover`.** It lists what's
  left — links with no source, citations not checked against their source,
  cited sources with nothing on file showing they were read, checks whose
  quote isn't in the stored text, findings waiting for approval, sections
  without prose or written before the model last changed, contradictions —
  each with how to fix it, and exits 1 until it's clear. Tell the person
  what's still on it.
- **Prose goes out of date.** When the model changes after a section was
  written, `interpret list`/`show`, the handover check and the report say so;
  run `latris interpret refresh-claims` and rewrite it.
- **If the Latris connector is available** (chat tools such as `create_model`
  and `get_report` from mcp.latris.app), use it rather than the CLI: its
  `report_url` is already a short link to share, and the model is saved from
  it with `get_save_link`. Use one or the other for a model, not both.
- **Otherwise give them `latris link`'s link** (`export md` also writes it under
  the diagram, fresh on every export). It opens the model in the Latris app
  as a hosted report with the full figure (loops, polarity, evidence) that
  they can share, and save to a free account for the editor and a Word
  report. Making it needs no network — the model travels inside the link —
  so it works from sandboxes that can't reach latris.app; opening it needs
  app.latris.app. The link never stops working; the short report address it
  opens lasts 30 days unless the model is saved, and saving gives a short link
  that doesn't expire (better for email and board papers).

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
