---
title: Directed Acyclic Graphs
category: model-types
summary: Use DAGs for acyclic causal or dependency structure where direction matters.
place: frame.model_type
---

## What a DAG represents

A Directed Acyclic Graph is a directed graph with no directed cycles. Following arrows from any node can never lead back to the same node.

## Best for

- Causal inference framing.
- Dependency analysis.
- Workflow or process logic where cycles are invalid.
- Foundations for Bayesian networks or causal DAGs.

## Required structure

DAG views require directionality and acyclicity. Feedback loops that are valid in a CLD must be reframed, split, or excluded from a DAG view.

## Analysis outputs

DAG analysis supports path enumeration, d-separation, Markov blankets, and adjustment-set reasoning. In the editor's Analyse pane, **Identification** takes a treatment and an outcome and lists every valid adjustment set; click one to see it on the canvas. **Effect estimate** (under Analyses) estimates the effect from a dataset.

## Estimating the effect

With a dataset (`latris data add survey.csv`, or the data workspace), `latris analyse estimate Exercise "Heart health" --dataset survey` estimates how big the effect is. Factors map to columns by name (or `--column "Exercise=exercise_hours"`). Latris adjusts for the smallest valid backdoor set the dataset measures — or a set you give with `--adjust`, which it checks against the DAG — and fits linear regression with robust standard errors for a numeric outcome, or logistic regression for a yes/no one. The unadjusted association is shown beside it, so you can see what adjustment changed. If every valid adjustment set needs a factor the data doesn't have, Latris names what to measure and estimates nothing.

The estimate is the effect only if the DAG leaves out no common cause, the model's form is right, and every kind of unit could receive every level of the treatment; the output and the report say so each time. The result is recorded and goes out of date when the DAG or the data changes.
