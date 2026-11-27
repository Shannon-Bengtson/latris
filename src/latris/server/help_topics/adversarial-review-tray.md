---
title: Adversarial Review Tray
category: ai
summary: The non-blocking docked panel where adversarial AI proposals accumulate for triage.
place: ai
---

## What it is

The Adversarial Review Tray is a docked panel (bottom-right of the workspace) where mutation proposals from Phase 3+4 prompts queue up for human review. It coexists with the single-proposal modal — the modal stays for one-at-a-time interactive runs, the tray accumulates proposals you want to triage in batches.

## Which prompts queue here

- **EdgeReclassify** (model-scope) — retags or removes misclassified edges.
- **ChallengeEdge** (element-scope) — counter-mechanism + a single repair action per edge.
- **EvidenceDemote** (element-scope) — verdict change or removal on an evidence link.
- **VerifyClaimAgainstSource** (element-scope) — source verification with apply-time verbatim check.

## How to use it

1. Run one of the adversarial prompts from the inspector or the model AI menu — the proposal lands in the tray rather than blocking with a modal.
2. Click an entry to expand it inline. The same picker components used by the modal render here.
3. Approve, reject, or close the entry. Approved proposals flow through the standard apply path; commits go through `auto_commit` and surface in git history.

## Non-blocking

The tray does not block the canvas. You can keep editing the model while proposals accumulate. Reject any time with the per-entry button or by closing the expanded view.
