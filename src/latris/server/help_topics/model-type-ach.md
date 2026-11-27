---
title: Analysis of Competing Hypotheses
category: model-types
summary: Weigh competing explanations against all the evidence at once, and find what the conclusion turns on.
place: frame.model_type
---

## What ACH represents

Several possible explanations (**hypotheses**) and everything you know that bears on them (**evidence items**: facts, reports, arguments, even things you'd expect to see and don't). Give each factor its element (`latris ach element <factor> hypothesis|evidence_item`), say how far each item can be trusted and how directly it bears (`latris ach item <item> --credibility high --relevance medium`), and rate every item against every hypothesis (`latris ach rate <item> <hypothesis> CC|C|N|I|II --rationale "…"`) — very consistent to very inconsistent. Ask of each cell: *if this hypothesis were true, how likely would I be to see this?*

An evidence item can carry its own sources like any factor (`latris evidence add <item> description <key>`), and the analysis says whether they've been checked.

## Base-case analysis

`latris ach analyse` (Heuer's method):

- ranks the hypotheses by the **evidence against them**, weighted by credibility and relevance — the strongest hypothesis is the one the evidence fails to rule out, not the one with most in its favour;
- flags evidence rated the same against every hypothesis — it can't help you choose;
- finds the **linchpins**: items without which the lead would change or be tied, with whether their sources were checked. Those are what to verify first.

The result is recorded for the report and goes out of date when a rating, weight or source changes.

## Practical caution

Ratings are judgements; record your reasoning (`--rationale`). The weights (high 1.0, medium 0.7, low 0.4; an inconsistency counts 1, a strong one 2) are a stated convention, and the ranking orders hypotheses — it doesn't give their probabilities. Method: Heuer (1999), *Psychology of Intelligence Analysis*, ch. 8.
