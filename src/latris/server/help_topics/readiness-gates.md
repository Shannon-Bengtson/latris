---
title: Readiness Gates
category: workflow
summary: What the red, yellow, and green phase indicators mean.
---

## What readiness checks do

Readiness checks look for the minimum material needed to move from one phase to the next. They are guardrails, not a judgement that the model is complete.

## Traffic lights

- **Red** means the next phase is blocked until required items exist.
- **Yellow** means the phase can be entered, but some important evidence, attributes, or review items are thin.
- **Green** means the project has the expected inputs for the transition.

## Typical blockers

- Home -> Build: no modelling question defined.
- Build -> Formalise: fewer than 3 nodes, or the graph is not a single connected network (orphan nodes or separate sub-graphs). A factor that has a role in a formal type (an MCDA option, a system-dynamics stock or flow) still joins the factors on either side of it; a group made only of such factors is not counted as an orphan.
- Formalise -> Analyse: no model type selected, a selected model is structurally incomplete (e.g. CLD without loops, DAG with a cycle), or required attributes (e.g. polarity for CLD, weights for FCM) are missing.
- Interpret -> Communicate: no structural summary with claims.

## How to resolve issues

Use the phase tools instead of working around the gate. Set the modelling question in the overview, add evidence anytime via the Data and References buttons, create entities and edges in Build, select and parameterise model types in Formalise, and generate prose in Interpret before using those sections in reports.
