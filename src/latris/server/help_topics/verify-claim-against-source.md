---
title: VerifyClaimAgainstSource
category: ai
summary: Apply-time verbatim quote validation against the stored source snapshot. The model cannot self-attest.
place: ai
---

## The audit invariant

When VerifyClaimAgainstSource returns `verdict="supports"`, the server checks that the model's quote appears in the text held for the source: a chunk of the fetched full text, the stored snapshot extract, or the abstract. Copying artefacts are forgiven (whitespace, curly quotes, dashes, case; `...` marks a gap); wording is not. On match, the link's `support_verdict` flips to `supports`, the quote and `quote_location` (chunk_hash + offset) land on the link with `quote_verified: true`, and `source_access` records what the quote was found in (`full_text_chunk` for the full text or a full-text excerpt, `abstract` for an abstract or summary). On mismatch, the proposal is rejected and the substrate stays unchanged.

The same check runs on `latris evidence check --by ai --quote ...` (and the chat connector's check): an agent cannot record a quote that isn't in the stored text. A person's check with a quote Latris can't find is recorded with `quote_verified: false`, and the report says the quote was not found.

The validator is the source of truth — not the model's confidence, not its prose. The model cannot self-attest.

## Other verdicts

- **contradicts** — the source addresses the claim and states the opposite. No quote required.
- **orthogonal** — the source is on-topic but does not address this specific claim. No quote required.
- **insufficient_extract** — the extract is too thin to decide. No quote required; prompt cycle ends with "needs deeper fetch".

For all three non-supports verdicts, no verbatim check runs — just the verdict flip.

## When to run it

After a reference has a `source_snapshot` (abstract or full text). If the snapshot is missing, the prompt's context builder raises before the LLM call — saves the API cost.

## How it flows in the GUI

1. Open the inspector for the node or edge that carries the evidence link.
2. Click the **Verify** button next to the link (disabled with a tooltip if no snapshot is set or the link is already verified).
3. Type the specific claim being verified — the AI gets it as input alongside the source snapshot.
4. The proposal lands in the Adversarial Review Tray. Approve to apply.

## CLI alternative

```
latris ai call run VerifyClaimAgainstSource \
    --inputs '{"target_id": "edge_xxx", "attribute": "polarity", "bibkey": "smith2023", "claim": "..."}' \
    --yes
```
