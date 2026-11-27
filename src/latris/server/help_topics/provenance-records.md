---
title: Provenance Records
category: provenance
summary: Use assumptions, decisions, questions, exclusions, predictions, sessions, and sign-offs to make reasoning auditable.
place: evidence
---

## What provenance records capture

Provenance records explain the reasoning around the model, not just the model structure.

## Record types

- **Assumptions:** things treated as true for modelling purposes.
- **Decisions:** unforced choices such as scope or modelling judgement calls.
- **Questions:** unresolved issues for later review.
- **Exclusions:** deliberate out-of-scope items.
- **Predictions:** expected observations if the model is right.
- **Sessions:** workshops, interviews, or elicitation activities.
- **Sign-offs:** formal review approvals.
- **Challenges:** arguments against a model element or claim.

## Best practice

Record why a choice was made, what it affects, and who was involved. This makes exports more credible and reduces the burden of reconstructing decisions later.

## Removing things keeps the history

Removing a node or link also removes what describes it — its description, confidence, polarity, citations, parameter values, roles and mappings — in the same change. Challenges, questions, sign-offs, assumptions, decisions and findings about it are kept: they are the record of what was argued and approved.

`latris check integrity` checks that every reference between the project's files resolves: no link to a missing node, no citation of a source that isn't in the library, no two nodes with the same name, no duplicate links. The handover check includes it. `latris check integrity --fix` clears rows left behind by older removals or hand edits.
