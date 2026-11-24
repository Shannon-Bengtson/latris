---
title: Bayesian Networks (quantitative)
category: model-types
summary: Discrete BN inference with hard and soft evidence, the most likely explanation, Monte Carlo over the tables, learning and sensitivity — with per-cell provenance.
---

## What a BN adds

A Bayesian Network quantifies an acyclic causal subgraph: every node gets a discrete **state space** and a **conditional probability table (CPT)** giving P(node | parents). You can then compute marginals and posterior queries — reasoning forwards (predictive) and backwards (diagnostic).

## The distinctive bit: per-cell provenance

Every CPT row carries its own provenance — `origin` (human-direct, human-elicited, data-derived, ai-proposed), `verification`, `source`, and who contributed. Different rows in one table can come from different sources (an expert, a dataset, a default), and the model shows where each number came from. No incumbent BN tool does this.

## Working with a BN (the `latris bn` commands)

- **`latris bn set-state-space <node> <states>`** — declare a node's discrete states (`--ordered` for ordinal).
- **`latris bn set-cpt <node> --parents … --probs …`** — fill a CPT (with `--origin`/`--source`).
- **`latris bn set-noisy-or <node> -c "<parent>=<state>:<prob>" --leak …`** — a *canonical model* for high-fan-in binary nodes: each cause contributes independently, so k causes need k probabilities + a leak instead of 2^k rows.
- **`latris bn set-weighted <node> --base 0.02,0.98 -w "Bloom=severe:3" -w "Barrier=failed:2.5"`** — a full table from a base distribution and a weight per parent state (logits; ±1 moderate, ±3 strong), for many-state parents where Noisy-OR doesn't fit. Every weight 0 gives the base in every row; a two-state node is logistic regression; `--toward` picks which end positive weights push to.
- **`latris bn remove-states <node>`** — take a factor out of the network (its states and table go; it stays in the loop map).

In the editor, a selected factor's pane has **Weighted table (many-state parents)** — the base distribution and a weight per parent state — and **Take out of the network**.
- **`latris bn learn <dataset>`** — fit CPTs from data. Rows you elicited or verified are **protected**; data fills only the gaps. Learned rows are stamped data-derived and the run is logged. In the editor: Formalise → **Learn the tables from data** previews what each table would become, then **Apply to the tables**.
- **`latris bn check`** — readiness: state spaces defined, CPTs complete + normalised, acyclic.
- **`latris bn marginals` / `latris bn query --evidence … --query …`** — exact inference. Each query is recorded (`--no-record` to skip); reports show the latest one per evidence set, posterior against prior, with a chart.
- **`latris bn sensitivity <target> --state …`** — rank the parameters that move a conclusion, flagging the ones that aren't human-verified.
- **Noisy-OR** — `latris bn set-noisy-or <node> -c "Cause=yes:0.6" --leak 0.02 --active yes`: `--active` names the node's state the causes push toward; it's required unless the first state is plainly the event (yes, true, present…).
- **Interventions** — `latris bn query --set "Barrier=upgraded"` asks what follows if we *make* it so (the do-operator), not what seeing it tells us: the factor's own causes stop mattering, so its causes' probabilities don't move. Reported as "given we set …".
- **Soft evidence** — `latris bn query -s "Wet=yes:0.8"` when you're not certain: afterwards P(Wet = yes) is 80% (Jeffrey's rule) and the other states share the rest. `--likelihood "Wet=yes:4,no:1"` instead says how much an observation favours each state.
- **`latris bn explain -e …`** — the single most likely combination of states given the evidence (MPE; `--over` limits it to chosen nodes, MAP), its probability, how many times likelier each state is than its runner-up, and where a node's own favourite differs from the combination.
- **`latris bn set-uncertainty <node> --n 20`** — how well a probability table is known: "worth about n observations" (`--row "Parent=state,…"` for one row). **`latris bn monte-carlo <target> [--state s] -e …`** then re-asks the query under seeded draws of every such table and gives the point estimate, median and the range 50% / 95% of draws fall in, the tables held fixed, and which tables drive the spread.
- **Scenarios (what-ifs that don't change the model)** — `latris bn set-scenario "Barrier upgraded" --table "Bloom reaches intake[Barrier=upgraded]=0.1,0.9"` saves new probabilities for the matching rows (`"Node=0.1,0.9"` for every row, or a root's only row); `--observe "Hot week=yes"` defines a situation, `--set` an intervention, `--soft`/`--likelihood` uncertain observations, `--extends OTHER` builds on another scenario. The model's own tables are untouched, so testing an upgrade never needs an edit and a revert. Use it with `bn query --scenario NAME` and `bn monte-carlo --scenario NAME` (the scenario's overridden rows and set factors are held at its values). `bn scenarios`, `bn remove-scenario`.
- **`latris bn compare <target> --state s -S OptionA -S OptionB`** — compare options: P(target = state) under the baseline network (no scenario changes) and each scenario. `-e` evidence holds for every option (a hot week, say). With table uncertainty, every option is asked on the *same* draws of the tables, so each difference (in percentage points) is paired, with the share of draws where it is lower or higher; without, point probabilities. Each row names its reference: an option extending a compared scenario is measured against it, the rest against the baseline; `--reference` sets one for all. Recorded as an options table in the report.

## Not yet

Decision and utility nodes (influence diagrams) and EVPI, ranked nodes / Noisy-MAX, continuous/hybrid nodes, structure learning, dynamic BNs, and incumbent-format import/export (which would strip provenance) are out of scope. See `docs/design/BN_QUANTITATIVE.md`.
