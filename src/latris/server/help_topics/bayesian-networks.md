---
title: Bayesian Networks
category: model-types
summary: Define state spaces and CPTs, then observe evidence and read posterior beliefs.
---

## What a Bayesian Network is

A Bayesian Network (BN) is a DAG where every node has a discrete **state space** and a **conditional probability table (CPT)** giving the probability of each state for every combination of its parents' states. Once parameterised, you can enter evidence and the network computes updated (posterior) beliefs for every node by exact inference.

## Parameterise in Formalise

Select **Bayesian Network** as a model type, then open the Formalise phase and select a node:

1. **State space** — list the node's mutually exclusive, exhaustive states (e.g. `low, high`). Mark it *ordered* for ordinal states. A node needs a state space before it can have a CPT.
2. **CPT table** — click *Edit CPT table* to open the spreadsheet. Each row is one combination of the parents' states; enter the probability of each of the node's states. Each row must sum to 1.0 — the Σ column flags rows that don't and offers one-click normalisation. Root nodes have a single prior row.
3. **Noisy-OR (optional)** — for a binary node whose parents are all binary, parameterise it compactly as Noisy-OR (a per-cause probability plus a leak) instead of a full table.

Every value carries provenance (where the number came from), so a BN built in Latris stays auditable.

## Analyse: evidence and beliefs

Open the Analyse phase with the BN view active. Each node shows **belief bars** — the posterior probability of each state. Click a state's bar on a node (or use the inspector) to **observe** it as evidence; beliefs update across the whole network. The observed node is badged, and the inspector shows the full posterior with a faint marker for the prior. Clear evidence on a node or clear the whole scenario at any time.

## Readiness

The Formalise → Analyse gate turns green once every BN node has a state space and a complete, normalised CPT. Until then the inspector lists what's missing.
