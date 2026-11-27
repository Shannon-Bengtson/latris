---
title: Bow-Ties
category: model-types
summary: Lay out the threats and consequences of one top event and the barriers between, and see where protection is thin.
place: frame.model_type
---

## What a bow-tie represents

A bow-tie centres on a **top event** — the moment control of a **hazard** is lost (e.g. *loss of containment* of *flammable gas under pressure*). On the left, the **threats** that could cause it, each on a line through the **prevention barriers** meant to stop it. On the right, the **consequences** that could follow, each through **mitigation barriers**. An **escalation factor** is a condition that degrades a barrier (a detector bypassed for maintenance); its own line runs through the barriers that control it.

Give each factor its element (`latris bowtie element <factor> hazard|top_event|threat|consequence|barrier|escalation_factor`) and draw the lines with ordinary links: threat → barrier → … → top event → barrier → … → consequence, and escalation factor → control → … → the barrier it degrades. Only factors with a bow-tie element are in it; a link from anything else is listed and left out.

## Barriers

Each barrier can carry its **type** (passive hardware, active hardware, active hardware + human, human — the CCPS types), its **status** (in place, degraded, not in place), its **owner**, and its **probability of failure on demand**, with where that number came from (`latris bowtie barrier <barrier> --type … --status … --owner … --pfd … --source …`). Only what you give changes.

## What the analysis shows

`latris bowtie analyse` lists every line with its barriers and flags:

- lines with **no effective barrier**, and lines resting on **one** (a degraded or missing barrier doesn't count);
- barriers on **more than one line** — one failure takes them all;
- escalation factors with **no control**, and barriers with **no owner**.

Give every threat a frequency per year (`latris bowtie frequency <threat> <f> --source …`) and every barrier on a line a failure probability, and it adds a layer-of-protection estimate: the top event's frequency, each consequence's, and for each barrier how many times more often its side's outcome would happen if it always failed (RAW). A barrier on two routes from the same threat is counted once. The important values nobody has verified are flagged. The analysis is recorded for the report and goes out of date when the bow-tie or a value changes.

## How sure is it? (Monte Carlo)

Give barrier failure probabilities and threat frequencies a range (`latris bowtie uncertainty "Pressure relief valve" --median 0.01 --error-factor 10`, or `uniform --min --max` and other distributions), then `latris bowtie monte-carlo`: the top event's and each consequence's frequency as a 5th–95th percentile range, median and mean beside the point estimate, and which ranges drive the spread. A barrier on several lines takes one value per run everywhere it appears, as it should.

## Calling it from a script (contract and predict)

Once it is quantified, a bow-tie can have a contract (see **Using a Model Elsewhere**). `latris contract init bow_tie` drafts one: threat frequencies and barrier failure probabilities go in, the top event's and each consequence's frequency come out (per year). A barrier also has its status as an input, so a caller can ask what happens if it is out without knowing its failure probability. The barrier then holds two inputs, so name the one you want by its cell: `latris contract input bow_tie "Gas detection" --cell bow_tie:status`, then `latris predict --set gas_detection_status=not_in_place`.

## Readiness

Complete when there is one top event, at most one hazard (linked to the top event), at least one threat and one consequence each on a line, every barrier on a line, every escalation factor linked to the barrier it degrades, and no link that breaks the pattern or loops.

## Practical caution

The quantification is LOPA's: order-of-magnitude and barriers assumed independent; values are points unless given a range for Monte Carlo. Escalation factors are not quantified, and there is no severity scale or risk matrix. The left side of a bow-tie is often a fault tree: a threat's frequency can cite a fault-tree analysis as its source. Methods: CCPS & Energy Institute (2018) *Bow Ties in Risk Management*, and CCPS (2001) *Layer of Protection Analysis*.
