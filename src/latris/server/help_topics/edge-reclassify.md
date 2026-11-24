---
title: EdgeReclassify
category: ai
summary: Adversarial pass that catches policy/governance/definitional links currently typed as causal.
---

## What it does

EdgeReclassify is a model-scope adversarial prompt. It scans every edge and proposes one of:

- **keep** — the edge is correctly typed.
- **retag** — change the edge's `kind` to `causal`, `decision_rule`, `governance`, or `definitional`. Non-causal kinds are excluded from loop counts and centrality analysis (`operations/graph_analysis.py::causal_edges`).
- **remove** — detach the edge with rationale.

## Why

The 4DWW capability run exposed an inflation bug: policy/decision-rule edges typed as causal inflated feedback-loop counts. EdgeReclassify is the repair pass — typing those edges as `decision_rule` keeps them on the canvas but out of loop counts.

## How it flows

1. Run from the model AI menu — queues to the Adversarial Review Tray.
2. Expand the proposal and review per-action checkboxes. Each action carries a rationale + confidence.
3. Approve the subset you accept. Rationale lands in the commit body.
