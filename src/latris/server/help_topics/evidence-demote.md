---
title: EvidenceDemote
category: ai
summary: Adversarial pass on one evidence link: change verdict or remove with rationale.
---

## What it does

EvidenceDemote runs on a single `(target, attribute, bibkey)` evidence link and asks whether the source actually supports the specific claim or only topically overlaps. Output is one of:

- **change_verdict(new_verdict)** — flip `support_verdict` to `unverified`, `contradicts`, `orthogonal`, or `insufficient_extract`. Rationale appends to the link's `notes`.
- **remove(rationale)** — detach the link entirely.

## What it never does

EvidenceDemote does NOT promote a verdict to `supports`. Promotion to `supports` happens only via VerifyClaimAgainstSource (Phase 4a), which enforces a verbatim-quote audit invariant. Demotion has no equivalent guarantee — the model's judgment is enough — so this prompt is one-way.

## How it flows

1. In the inspector, find the evidence entry on a node or edge, click "AI demote" — queues to the Adversarial Review Tray.
2. Review the AI's reasoning. Verdict change applies via the new `set_evidence_support_verdict` operation.
