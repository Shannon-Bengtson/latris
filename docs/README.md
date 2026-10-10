# Docs — Latris

Engineering reference for Latris — an evidence-native modelling
workbench. This repository holds the open-source core (the `latris`
Python package: CLI + API server). The Latris desktop app is built on
this package from a separate private repository. Start at the repo-root
[README](../README.md).

## What Latris is (and isn't)

**Is:**
- A Python CLI (`latris`) + FastAPI server backend that scaffolds a
  modelling project, lets you author a structured, inspectable
  causal/systems model qualitatively, attaches evidence and provenance,
  commits every change to Git automatically, talks to an LLM through a
  vendor-agnostic adapter under human approval, and produces defensible
  review/report artefacts.
- All 46 canonical AI prompts wired end-to-end across 10 categories
  (authoring, scrutiny, scope, evidence, output, references, provenance
  assist, compose, interpret, configure).
- Data wrangling (39 pandas operations with versioning and audit trail),
  references management (BibTeX import + DOI import + Semantic Scholar
  search), table view for systematic review, lineage/versioning, model
  type registry with readiness gating, graph analysis (CLD loop
  detection + polarity propagation; DAG d-separation, Markov blanket,
  path enumeration, adjustment sets).
- A discrete Bayesian Network engine: state spaces, CPTs with per-cell
  provenance, exact inference (pgmpy), Noisy-OR canonical models,
  parameter learning from data, provenance-aware sensitivity analysis —
  via CLI `bn` + `/api/bn/*`.

**Isn't yet (deferred — on the architecture's path):**
- A *general* quantitative modelling engine. ODE simulation, regression
  fitting, causal identification, and a Monte Carlo / PSA analysis layer
  are deferred. The discrete BN engine above is the quantitative
  beachhead.

**Isn't ever (excluded by design — fails the inspectability test):**
- Black-box predictors you can run but can't inspect or defend (random
  forests, gradient boosting, neural nets), and opaque structure
  learning. Latris admits a model type only if its reasoning stays
  inspectable.

## Documentation structure

### Engineering (`engineering/`)

How it's built. For developers working on the codebase — and for AI
agents: read these before changing code.

1. [`ARCHITECTURE.md`](engineering/ARCHITECTURE.md) — three-layer
   architecture, module layout, repository layout, CLI ↔ GUI boundary,
   the five chokepoint files.
2. [`SCHEMA_NOTES.md`](engineering/SCHEMA_NOTES.md) — pydantic models
   to YAML mapping; provenance origin/verification axes; source-id
   reference pattern.
3. [`GIT_INTEGRATION.md`](engineering/GIT_INTEGRATION.md) — auto-commit,
   identity enforcement, semantic diffs, collaboration model.
4. [`AI_LAYER.md`](engineering/AI_LAYER.md) — LLM wiring (litellm +
   instructor + keyring), credentials, call flow, testing, mock mode.
5. [`TESTING.md`](engineering/TESTING.md) — test strategy, layers,
   hermetic contract, how to add tests.
6. [`CLI_REFERENCE.md`](engineering/CLI_REFERENCE.md) — the `latris`
   command catalogue.

### The worked example (`../worked_example/`)

Living acceptance test: `worked_example.py` exercises every CLI command
end-to-end and generates `worked_example_output.md`, a transcript that
always shows the tool's full current capabilities. Regenerate with
`pytest tests/test_worked_example.py --slow` after changing CLI
behaviour; commit both the script change and the transcript.

## Install (developer)

Prerequisites:
- Python 3.11+ on PATH.
- `git` 2.40+ on PATH, with `user.name` and `user.email` configured globally.

```
python -m venv .venv
# Windows: .venv\Scripts\activate   —   mac/linux: source .venv/bin/activate
pip install -e ".[server,data,dev]"
latris --version
latris doctor
```

Plain `pip install "latris[server,data]"` works from PyPI once a release
is published.

## First run

```
latris init demo --question "Does X cause Y in context Z?"
cd demo
latris node add "Price"
latris node add "Demand"
latris edge add <price-id> <demand-id> --kind causal
latris status
latris log
```

(Full command catalogue in [`CLI_REFERENCE.md`](engineering/CLI_REFERENCE.md).)
