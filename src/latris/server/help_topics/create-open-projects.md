---
title: Create and Open Projects
category: getting-started
summary: How projects are created, what a project contains, and what must be configured first.
---

## Project foundations

Every project starts with a modelling question or decision statement. This foundation tells the app, the AI prompts, readiness checks, and exports what the model is meant to answer.

## Requirements

Latris uses Git under the hood for version history and human accountability. You do not need to understand Git commands or workflows; the app presents history as versions, milestones, alternatives, compare, and undo.

## Project contents

A Latris project contains:

- `project.yaml` for the foundation and selected model types.
- `research-base/` for references and notes.
- `substrate/` for conceptual entities, edges, attributes, mappings, and evidence links.
- `views/` for formal views such as CLD, DAG, and FCM.
- `data/` for registered datasets, versions, and data action logs.
- `provenance/` for assumptions, decisions, questions, sign-offs, sessions, predictions, and exclusions.
- `ai/` for AI interactions and challenge records.
- `reports/` for draft reports and generated report content.

## First practical path

1. Create or open a project from the landing page.
2. Set the modelling question in the project overview.
3. Build the conceptual model.
4. Move through Build, Formalise, Analyse, Interpret, and Communicate & Use. Data and References are always available as the evidence basis.
