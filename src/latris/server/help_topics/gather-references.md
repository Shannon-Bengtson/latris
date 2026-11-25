---
title: References Workspace
category: evidence
summary: Import, search, review, and reuse citations as project evidence.
---

## What References mode is for

References mode is the project bibliography and evidence base. References can come from BibTeX, DOI import, manual entry, or scholarly search.

## Main tasks

- Import BibTeX records.
- Import a source by DOI when metadata is available.
- Search for scholarly references.
- Review titles, authors, years, identifiers, abstracts, and URLs.
- Use references as citations for attributes on nodes and edges.

## Evidence links

A reference becomes evidence only when it is attached to a specific claim or attribute. Attach citations in the inspector so reviewers can see exactly what a source supports.

## Source snapshots

A reference can carry a `source_snapshot` recording publisher-fetched content (abstract, landing-page text, or a full-text excerpt) with retrieval URL, fetch timestamp, and content hash. This is distinct from the user-authored `notes` field.

When attaching evidence, the system promotes `source_access` from `title_only` to `abstract` only when the reference has a real abstract or an abstract / full-text snapshot. User notes alone and landing-page-text snapshots do **not** confer abstract-grade access — they may discuss topical context but they are not the paper's content.

## Practical advice

Keep references broad enough to support the model, but attach them narrowly. A paper might support a node definition, an edge direction, a polarity judgement, or a confidence rating; those are different claims and should be linked separately when possible.
