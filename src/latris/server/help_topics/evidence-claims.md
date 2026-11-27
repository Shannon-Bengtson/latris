---
title: Evidence and Claims
category: evidence
summary: How references and datasets support specific model attributes.
place: evidence
---

## Evidence is claim-level

Latris does not treat a reference as evidence for an entire node or edge by default. Evidence attaches to specific attributes.

## Examples

- A report supports a node description.
- A paper supports an edge direction.
- A dataset statistic supports a confidence judgement.
- Expert elicitation supports a polarity or weight.

## Audit axes on evidence

Each evidence link carries four orthogonal axes so a reviewer can answer four separate questions about it:

- **Who proposed it?** `verified_by`: human or ai.
- **What did the proposer see?** `source_access`: title only, abstract, full-text chunk, or full text.
- **Does the source actually support the specific claim?** `support_verdict`: unverified, supports, contradicts, orthogonal, or insufficient extract — the result of someone reading it.
- **Is it offered for the claim or against it?** `stance`: for or against. Citing a source as against a claim (`--contradicts`) sets the stance; it stays unchecked until someone reads it.
- **Where exactly?** `quote` plus `quote_location` (chunk hash, page, offset), and `quote_verified`: whether the quote was found in the text held for the source.

A single ai-verified or human-verified badge conflated these — an AI-suggested link with no source access could read as if it had been verified against the paper. The split makes the difference visible.

## Evidence against a link

A source that argues against a claim goes on the same link, marked as contradicting: `latris evidence add <link> polarity <bibkey> --contradicts` (or `contradicts: [<bibkey>]` on a link in `latris build --spec`). It doesn't count toward evidence coverage. Reports list it as **against**, a "Contested links" section shows each disputed link's sources for and against (with any open challenge on it), and the confidence and open-questions claims name the disagreement. A challenge is different: it's a person disputing something, and it can stand alongside contradicting sources.

## Why this matters

A defensible model needs to show which exact claim is supported and who accepted it. Broad evidence lists are weaker than targeted evidence links.
