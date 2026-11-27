---
title: Fuzzy Cognitive Maps
category: model-types
summary: Use FCMs for weighted causal influence and semi-quantitative scenario reasoning.
place: frame.model_type
---

## What an FCM represents

A Fuzzy Cognitive Map is a weighted directed graph. Each edge has a causal strength, commonly in the range -1 to +1. Positive values reinforce; negative values counteract.

## Best for

- Participatory modelling.
- Expert-driven scenario exploration.
- Semi-quantitative causal influence.
- Systems where feedback exists but full equations are not available.

## Required attributes

FCM analysis depends on edge weights and, for simulation, node activation settings. Missing weights reduce readiness. `latris fcm weights` lists the weights set so far.

## Commands

- **`latris fcm set-weight <edge> <weight>`** — a link's influence, from -1 (strongly opposes) to +1 (strongly drives).
- **`latris fcm weights`** — every weight.
- **`latris fcm infer`** — run the map to its steady state (which factors end up high or low); `--clamp 'Factor=1.0'` holds a factor at a value as a scenario. Each run is recorded (one result per scenario) and shows in the report and under **Recorded results**; `--no-record` only shows it. In the editor, Analyse → **Steady state** runs it, with the factors to hold picked from the map.

## Calling it from a script (contract and predict)

A weighted map can have a contract (see **Using a Model Elsewhere**). `latris contract init fcm` drafts one: factors that nothing drives become inputs a caller holds at an activation (a scenario), and factors that drive nothing (or the marked outcome) become outputs, as their activation at steady state. `latris predict -m fcm --set transport_policy_held_at=1` runs the scenario. A starting activation can be an input too. Activations are relative, from 0 to 1, so compare scenarios rather than reading the levels as amounts. A map that doesn't settle returns where it stopped, with a warning.

## Practical caution

FCM weights are judgement-rich. Link weights to elicitation, evidence, or rationale so they are not mistaken for measured parameters.
