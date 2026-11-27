---
title: Causal Loop Diagrams
category: model-types
summary: Use CLDs for feedback structure, polarity, and reinforcing or balancing loops.
place: frame.model_type
---

## What a CLD represents

A Causal Loop Diagram is a directed graph where edges carry polarity. A positive edge means the source and target move in the same direction, all else equal. A negative edge means they move in opposite directions.

## Best for

- Feedback-rich systems.
- Policy and systems thinking.
- Explaining reinforcing and balancing loops.
- Early-stage system dynamics work.

## Required structure

A CLD must contain at least one feedback loop. Loops are the defining feature of the formalism — an acyclic directed graph is a causal map or DAG, not a CLD. Readiness for a CLD will not pass until at least one loop closes.

## Required attributes

CLD analysis depends on edge polarity. Missing polarity weakens readiness and prevents useful loop classification.

A polarity can carry its reason — the causal story for the sign ("more cars, more exhaust"). In the app it sits under the link's polarity in the inspector, where you can edit or remove it. If you change a link's sign and leave a written reason as it was, Latris opens a question on the link: the reason was written for the other sign and may now argue against it. Editing the reason or removing it answers the question, and Latris closes it for you; until then it shows with the link's other open questions and in the report. Undo takes the sign change and its question back together.

## Analysis outputs

CLD analysis can identify cycles, classify loop polarity, and support polarity propagation through paths.
