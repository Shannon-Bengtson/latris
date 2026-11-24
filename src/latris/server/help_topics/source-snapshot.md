---
title: Source Snapshots
category: evidence
summary: A persistent fetched-content slot on each Reference, with metadata that the verifier audits against.
---

## What it is

`Reference.source_snapshot` records the text the project actually has access to for a citation: `retrieval_url`, `fetched_at`, `content_hash`, an extract (≤2000 chars; a longer one is refused — keep the passage that bears on the claim), and a `kind` discriminator.

## Three kinds

- **`abstract`** — the paper's abstract or a short summary you (or `ref snapshot`) pasted in. Promotes `EvidenceLink.source_access` to `abstract`.
- **`landing_page_text`** — generic publisher landing-page copy. Does NOT promote source_access — landing pages are not the paper's content.
- **`full_text_excerpt`** — created by `ref fetch` (Tier-1). The first 2000 chars of the fetched full text; the rest lives in a per-bibkey artefact at `ai/reference-extracts/<bibkey>.txt`.

## How it's set

- **Manual**: `latris ref snapshot <bibkey> --url ... --extract ... --kind abstract`. Use this when the source is paywalled, behind a login, or otherwise unreachable to the fetcher.
- **Automatic**: `latris ref fetch <bibkey> [--url ...]` or the "Fetch source" button in the Reference Inspector. See Tier-1 retrieval.

## Why it matters

VerifyClaimAgainstSource validates the AI's verbatim quote against `source_snapshot.extract` (Phase 4a) or against the per-bibkey artefact's chunks (Phase 4b). No snapshot, no verification — the prompt refuses to run.

## Refetch behaviour

Refetches overwrite the snapshot. Git history preserves prior snapshots; the YAML always reflects the latest fetch.
