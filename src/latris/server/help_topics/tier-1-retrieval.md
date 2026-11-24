---
title: Tier-1 Source Retrieval
category: evidence
summary: `ref fetch` pulls the full text of a reference, chunks it, and stores it as a per-bibkey artefact.
---

## What `ref fetch` does

1. **Resolves the URL** — explicit `--url`, then `Reference.url`, then `https://doi.org/<doi>`.
2. **Fetches via httpx** with redirect follow, timeout, and a Latris user agent.
3. **Extracts text** — HTML is tag-stripped (no BeautifulSoup dep); `text/plain` passes through; `application/pdf` uses `pypdf` if installed.
4. **Writes the artefact** at `ai/reference-extracts/<bibkey>.txt` (gitignored). Each Reference has at most one artefact; refetches overwrite.
5. **Updates `Reference.source_snapshot`** with `kind="full_text_excerpt"`, first 2000 chars as the extract, retrieval URL, fetched_at, and the content hash of the full text.

## How verification uses it

When VerifyClaimAgainstSource runs and the artefact exists, the context builder chunks the full text (1000-char windows with 200-char overlap), scores chunks against the claim with BM25-lite keyword overlap, and passes the top-3 chunks to the model. The verbatim-quote check then matches against the specific chunk whose `content_hash` the model returns.

## What it doesn't do

- **No PDFs without pypdf.** The fetcher raises with a clear message if PDF content arrives without pypdf installed. `pip install pypdf` to enable.
- **No paywall bypass.** Login gates and 403 responses cause empty-text rejections; use `ref snapshot` to paste content manually instead.
- **No Tier-2 discovery.** Auto-discovery via Semantic Scholar / OpenAlex / arXiv at proposal time is a separate (deferred) feature.

## Hermetic tests

Tests inject a stub via the `http_get` parameter on `fetch_reference_source`. No network in CI; see `tests/operations/test_fetch_reference.py`.
