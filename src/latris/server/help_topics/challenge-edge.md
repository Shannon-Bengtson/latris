---
title: ChallengeEdge
category: ai
summary: Element-scope adversarial prompt: counter-mechanism plus one repair action per edge.
place: ai
---

## What it does

ChallengeEdge runs on a single edge and returns the strongest counter-mechanism against the edge as encoded, plus one of three repair actions:

- **evidence_search(query)** — record a literal search query as an OpenQuestion for human pickup.
- **polarity_flip(new_polarity)** — flip the CLD polarity on the edge (`+`, `-`, or `~`).
- **remove(rationale)** — detach the edge entirely.

## Why one action

The asymmetry of Phase 3 is closed: the AI can propose to demote prior-approved state, but only via a single, structured action that goes through `apply()`. The reviewer triages.

## How it flows

1. Open the edge inspector, click "Challenge edge (adversarial)" — the proposal queues to the Adversarial Review Tray.
2. Review the counter-mechanism prose, then the proposed action. Rationale + confidence travel together.
3. Approve to apply, reject to discard.
