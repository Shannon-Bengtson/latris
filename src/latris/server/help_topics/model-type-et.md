---
title: Event Trees
category: model-types
summary: Follow one initiating event forward through yes/no headings to end states, with the probability of each.
place: frame.model_type
---

## What an event tree represents

An event tree starts from one **initiating event** (a gas release) and asks, in order, a series of yes/no questions — the **headings** or functional events (*Gas detected?*, *Isolation succeeds?*, *Ignition?*). Each complete path of answers is a **sequence**, and each sequence ends in an **end state** (*contained release*, *fire*, *gas cloud dispersed*). A branch need not ask every heading: once isolation succeeds, ignition may not matter.

Give each factor its element (`latris et element <factor> initiating_event|functional_event|end_state`), set the heading order (`latris et order <heading> …`), then add each sequence with its answers and end state (`latris et sequence Fire "Gas detected=no" "Ignition=yes"`). The tree isn't drawn with links: one heading is asked on many branches, so the structure is stored as data.

## Probabilities

Each heading has P(yes) (`latris et probability <heading> <p>`), and can have different values on different branches (`--given "Gas detected=no"`): the most specific value that matches a branch applies. The initiating event can have a frequency per year (`latris et frequency`). Every value keeps where it came from; a heading's probability can cite a fault-tree analysis, and the initiating frequency a bow-tie's.

## Base-case analysis

`latris et analyse` gives each sequence's probability (the product of its branch probabilities) and, with the initiating frequency, how often it happens per year; the totals per end state; and the dominant sequence behind each end state. Values on the dominant sequences that nobody has verified are flagged. The result is recorded for the report and goes out of date when the tree or a value changes.

## Uncertainty analysis (Monte Carlo)

Give the uncertain numbers a range and sample them: `latris et uncertainty "Gas release" --median 0.02 --error-factor 3` (a lognormal whose 95th percentile is three times its median — the usual way risk assessments state it), or a branch probability, conditional ones with `--given "Gas detected=no"`; other distributions take `uniform --min --max`, `triangular`, `beta` and so on. `latris et monte-carlo` reruns the tree for each sample and gives every end state's 5th–95th percentile, median and mean beside the point estimate, and ranks the uncertain inputs by how strongly they drive the headline end state (`--output` picks it; by default the rarest). Values without a range stay fixed and are listed, so the spread is a lower bound.

## Sensitivity analysis (global)

`latris analyse global-sensitivity event_tree` varies every heading probability and initiating frequency that has a range together and gives each one's share of the variance in the result, alone (S1) and through its interactions (ST), from Sobol indices; `--method morris` is a cheaper screen. An input with ST near zero could be fixed anywhere in its range. It needs two or more ranges, and the result is recorded for the report (see the Analyse Canvas topic).

## Calling it from a script (contract and predict)

Once it is quantified, an event tree can have a contract (see **Using a Model Elsewhere**). `latris contract init event_tree` drafts one: the initiating event's frequency and every branch probability go in, and the rarest end state's frequency comes out (add others with `latris contract output event_tree <end state>`). A heading with a different probability on different branches has one input per branch, named after the branch, e.g. `p_ignition_yes_gas_detected_no`. `latris contract available event_tree` lists them.

## Readiness

Complete when there is one initiating event and at least one end state, every heading is in the order, and the sequences form a complete tree: at each branch point every sequence asks the same next question, both answers are covered, no sequence stops while a sibling continues, and every heading and end state is used.

## Practical caution

Branches are binary, and dependence between headings is only what you state with conditional probabilities. Uncertainty comes only from the ranges you give for Monte Carlo, and heading probabilities are entered rather than linked live to fault trees. Methods: IEC 62502 (event tree analysis) and the NRC *PRA Procedures Guide* (NUREG/CR-2300).
