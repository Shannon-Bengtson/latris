---
title: The Formalise Phase
category: formalise
summary: Select model types and set their parameters before analysing.
---

## What Formalise is for

Formalise turns your conceptual structure into a complete formal model. Choose the model types you want from Model selection, then parameterise each one.

## Per-model workspaces

Each selected model type appears in the Formalise dropdown. With a model open you work in the representation(s) that type offers:

- **Table** — a parameter grid for setting model-specific attributes (CLD polarity, FCM weights).
- **Canvas** — the structure, drawn the way the report's figure draws that type, with the selected element's parameters in the inspector: Bayesian networks (states and probability tables), system dynamics (roles, equations and values), decision trees (decision, chance and payoff nodes; each branch's option or state, probability and value), Markov models (states, moves per cycle, costs, utilities, the starting cohort and the clock), equation models (each quantity's role, value or formula, units, valid range and uncertainty) and theories of change (each factor's level; process-tracing priors and evidence tests on links).
  Fault trees (event types, gates — AND, OR, k of n — and basic-event probabilities) and bow-ties (threats and their frequencies, barriers with type, status, owner and failure probability, the top event and consequences) are set here too, with a median and error factor for any value whose uncertainty you know.
- **Matrix** — MCDA (options, criteria, swing weights and the score grid), ACH (hypotheses, evidence, credibility, relevance and the consistency grid) and event trees (the initiating frequency, the headings in order with their probabilities — conditional ones too — and each sequence's end state). These have no links: Build doesn't ask for their elements to be connected, and the other types' canvases leave them out.

## Moving on

The Formalise -> Analyse gate turns green once at least one model type is fully parameterised. Analyse then lets you interrogate that model on its canvas.
