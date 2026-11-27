---
title: Analyse Canvas
category: analyse
summary: View formal model analysis overlays without changing the Build canvas.
place: analyse.structural
---

## What the Analyse canvas is for

The Analyse canvas mirrors model structure but adds analysis overlays and formal-view context. It keeps analytic reading separate from direct model authoring.

## Supported stable views

- **CLD:** feedback loop detection, loop polarity, and polarity propagation.
- **DAG:** acyclicity checks, paths, d-separation, Markov blankets, and adjustment-set support.
- **FCM:** weighted influence structure and simulation-oriented attributes.
- **BN:** observe evidence on nodes and read posterior beliefs, shown as bars inside each node (see the Bayesian Networks topic).
- **SD:** run the simulation (with saved scenarios to compare), Monte Carlo, sensitivity and loop dominance from the analysis pane; each factor shows its end-of-run value on the canvas (see the System Dynamics topic).
- **BN, beyond evidence:** *set* a factor (a policy, not an observation), apply a saved scenario, record the query, find the most likely explanation, run sensitivity, Monte Carlo over the tables (after saying how well each table is known) and compare scenarios.
- **Decision tree, Markov, theory of change:** roll back the tree, run the cohort, or check the theory and run process tracing from the analysis pane; for decision trees and Markov models, a probabilistic sensitivity analysis over the ranges you set.
- **Equation model:** evaluate the formulas (with saved scenarios), sweep an input, and run Monte Carlo over the ranges you set, from the analysis pane.
- **MCDA, ACH:** run the analysis from the matrix page; its charts, tables and the report's figure show there.
- **Fault tree, bow-tie, event tree:** analyse (cut sets and importance; consequence frequencies through the barriers; end-state frequencies), then Monte Carlo over the ranges you set.
- **Global sensitivity (fault trees, bow-ties, event trees, decision trees, Markov, SD and Bayesian-network models):** once two or more inputs have a range, see which the result's uncertainty comes from — `latris analyse global-sensitivity <model type>`. **Sobol indices** (the default) give each input's share of the result's variance on its own (S1) and with its interactions (ST), with 95% intervals; an input with ST near 0 could be fixed anywhere in its range without changing the spread, so narrowing its range buys nothing. **Morris screening** (`--method morris`) ranks the inputs in far fewer runs: μ* for influence, σ near or above μ* for interaction or a non-linear effect. The headline result is the model's main one — the top event, the best option's advantage over the runner-up, the net benefit at the willingness to pay — or `--output`; SD takes `--variable` and `--metric`; a Bayesian network takes `--variable`, `--state` and `--evidence`, and treats each probability table you've said how well is known as one input (as it does a chance node's branches or a state's transitions out). Recorded with a chart.

Nodes take the shapes the report figure gives them — stocks as boxes, flows with a valve, sources and sinks as dashed clouds, BN nodes as belief-bar monitors — so the editor and the report read the same.

## Recorded results

Runs that are recorded (simulations, Monte Carlo, sensitivity, loop dominance, recorded BN queries and every other model type's analyses) are listed under **Recorded results** in the pane on the right. Click one to read it at full width over the canvas or table, with the same charts and tables the report shows; **Close** or Escape returns. Each says if the model has changed since it ran ("Out of date"), and **Hide from report** leaves it out of reports (the same as `latris results hide`).

Under **Analyses** (or **More analyses**), the pane offers every other analysis Latris has for the model type as a form — DAG effect estimates, theory-of-change impact, fuzzy-cognitive-map steady states, Bayesian-network queries with uncertain evidence or interventions, system-dynamics option comparisons under uncertainty, and any added later. Each option is labelled and explained; factors, states, scenarios, datasets and columns are picked from the model. **Run** records the result and opens it.

MCDA, analysis of competing hypotheses and event trees are edited as grids in the centre; their readiness, **Run the analysis** and recorded results are in the pane on the right, as for every other model type. Click a factor's name in a grid to show its details there.

## Workflow

1. Select a model type.
2. Review readiness for that view.
3. Run or inspect available analyses.
4. Record your reading in **Observations** (see below).
5. Use findings as inputs for Interpret.

## Observations

The analysis pane carries an **Observations** section on every formalism — when nothing is selected (a project-level reading) and when a node or edge is selected (a reading of that element). Record what you see in the analysis here: each observation is saved as a finding, committed with provenance, and flows into the matching Interpret section's claims. Element-anchored observations are flagged if the element they reference later changes. Pick a category (structure, sensitivity, inference, etc.) so the observation lands in the right report subsection.

## Editing

Use Build for core graph edits. Use Configure for model-specific attributes such as CLD polarity or FCM weights.
