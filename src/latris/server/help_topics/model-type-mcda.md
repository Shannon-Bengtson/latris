---
title: Multi-Criteria Decision Analysis
category: model-types
summary: Choose between options judged on several criteria, and see how firm the choice is.
place: frame.model_type
---

## What an MCDA represents

Options you could choose (sites, suppliers, policies) and the criteria they are judged on (cost, travel time, capacity). Give each factor its element (`latris mcda element <factor> option|criterion`), then for each criterion a **swing weight**, a **direction** and, ideally, a **scale** (`latris mcda criterion Cost --weight 50 --direction lower --worst 100 --best 0 --units "$m"`), and each option's **score** on each criterion (`latris mcda score "Site A" Cost 40 --source quote-2025`).

A swing weight says how much moving from the worst to the best of the scale matters, compared with the other criteria's swings — so a weight means nothing without its scale. Without `--worst`/`--best` the options' own range is used; that shifts when an option is added, and the weights then need revisiting.

## What the analysis shows

`latris mcda analyse` turns each score into a value from 0 (worst) to 1 (best), combines them by the normalised weights into a total out of 100, and shows:

- the **ranking**, with each criterion's contribution to each option's total;
- **dominated** options — no better anywhere, worse somewhere — which can be set aside whatever the weights;
- for each weight, **how far it would have to move** (the others keeping their proportions) before the top choice changes — a fragile choice shows up as a small move;
- the scores the winning margin rests on that nobody has verified.

The result is recorded for the report and goes out of date when a weight, scale or score changes.

## Calling it from a script (contract and predict)

A complete MCDA can have a contract (see **Using a Model Elsewhere**). `latris contract init mcda` drafts one: the criteria's weights go in, and each option's overall value (0–100) and the top option come out. Weights are relative, so `--set cost_weight=10 --set travel_time_weight=80` means "travel time counts eight times as much". An option's score on a criterion can be an input too (`latris contract available mcda`). On a criterion without a fixed scale, changing one score moves every option's value, and the run warns you. Fix the scale (`--worst`, `--best`) before comparing runs.

## Practical caution

The model is additive and linear: it assumes criteria can be traded off independently and value rises evenly between worst and best. Weights are judgements — record whose (`--source`). Methods: Keeney & Raiffa (1976), Belton & Stewart (2002), and the UK government's *Multi-criteria analysis: a manual* (DCLG 2009).
