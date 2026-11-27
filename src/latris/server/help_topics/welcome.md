---
title: Welcome to Latris
category: getting-started
summary: What Latris is, what it is for, and the ideas that make the workspace hang together.
place: project
---

## What Latris is

Latris is an evidence-native modelling workbench for building, reviewing, analysing, and reporting on models you have to defend: causal and systems models, and models for evaluation, risk, decisions, arguments and equation-based calculation. It keeps the model, evidence, provenance, AI assistance, version history, and exported outputs in one auditable project.

## Core ideas

- **Inspectability is the boundary.** Latris is for models whose reasoning can be inspected, evidenced, challenged, and defended. The graph is *how* a model is made inspectable — the lens, not the limit. Models you can run but can't explain (black-box predictors) are out of scope by design.
- **Substrate first.** The shared conceptual model is the source of truth for entities, edges, definitions, evidence, and review history.
- **Formal views second.** Each model type (a causal loop diagram, a Bayesian network, a fault tree, a decision tree and the rest) is a projection from the shared substrate with model-specific rules and attributes.
- **Evidence attaches to claims.** Citations and data links attach to attributes such as definitions, confidence, polarity, and weights.
- **AI is reviewable.** AI drafts suggestions, but the user previews, accepts, rejects, and audits what lands in the project.
- **Every change is versioned.** Project state is stored in files and committed through Git-backed history.

## Main workspace

Use the process stepper across the top of the app:

1. **Frame** the question, its audience, and which model types to build.
2. **Build** the conceptual model.
3. **Formalise** each model type: its definitions, values, ranges and scenarios.
4. **Analyse** each model, from structural and base-case analysis to uncertainty and sensitivity.
5. **Interpret** findings into claims and prose.
6. **Communicate**: reports, diagrams, review packs, stories and explorers for readers.
7. **Use**: a contract for code that runs the model.

Evidence (Data and References) is always available alongside the stepper: it is a track beside every stage, not a stage (see "The Workflow").
