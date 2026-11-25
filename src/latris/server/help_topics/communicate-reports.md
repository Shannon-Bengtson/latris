---
title: Report Builder
category: communicate
summary: Assemble report sections and export Markdown or Word deliverables.
---

## What Report mode is for

Report mode assembles project material into exportable documents. It combines project data, model structure, provenance, evidence, findings, and Interpret-phase prose.

Reports are per-formalism: the report is scoped to the formalism chosen in the process stepper. The model structure, findings, and interpretation are filtered to that formalism's view; project-level material (evidence, references, history) is shared. Each formalism remembers its own section selection, voice, and depth.

## Section types

- Foundation.
- Nodes and edges.
- Evidence and references.
- Assumptions, decisions, questions, exclusions, predictions, sign-offs, and sessions.
- Challenges and findings.
- Datasets and data actions.
- Milestones.
- Methods and foundations — the established methods the model relies on, each cited with its source and stated limits, generated from the foundations registry so it cites only methods the report actually used.
- Interpret-generated prose sections.

## Reports for readers

The **client** and **publication** packs are written for people outside the modelling work, and are grouped into parts in reading order: **Summary** (the answer, the model's size and approved findings), **The model** (the diagrams), **What the analysis shows** (current results and the findings written up from them), **How confident we are** (confidence, contested links, what the person reviewed at each checkpoint of an AI-built model, assumptions and exclusions) and a **Technical appendix** (links, factors, evidence, methods and references). They show only what's ready for a reader: interpretation sections that have been written up (one section per heading, with a paragraph per model type), results computed on the model as it is now — with one line saying how many earlier ones there are — and approved findings. They leave out internal IDs, who recorded each assumption and when, and the change log. The review, workshop and audit packs keep everything.

## Export formats

Use Markdown for transparent text output and Word for stakeholder-ready documents. The Markdown report opens with a Mermaid sketch of the model, which GitHub and most chat tools draw as a diagram. **Build spec (.json)** exports the model itself — factors, links, sources, the model type's values and its analyses — as `latris export spec` does; `latris build --spec` (or a chat with the Latris connector) rebuilds it elsewhere.

## Ready to share?

With no report section selected, Communicate's inspector shows **Ready to share?** — what's left before the model goes to a board: links with no source, citations nobody has checked, sources with nothing on file showing they were read, findings waiting for approval, report sections unwritten or out of date, results computed before the model last changed, model types with no recorded reason, a type's own check, and broken references between files. Each item says what to do; its link takes you to the place to do it, with the factors and links concerned selected (or, for a source, References with that source open). Check a citation under the link's **Citations** with **Check…** — what the source says, a passage copied from it, and whether it supports the claim, argues against it, is off topic or too short to tell — or remove it there. Save the passage you read of a source with **Save what you read…** in References; a check's quote is looked up in it. Broken references between files have a **Remove leftover rows** button. Once nothing is left, record a **sign-off** (your role, and what you're signing off). A factor's or link's **Maturity** (proposed, reviewed, approved) is set in its inspector; approving asks for your role and records a sign-off too. The arrow into Communicate is the same check: green once the list is empty, amber while anything is left. From the command line: `latris check handover`.

## Importing a build spec

**Import a build spec** (command palette, or the link in the Export dialog) builds a spec — YAML or JSON — into the open project. Factors, links and sources the project already has are used as they are; the spec only fills what they lack (an empty description, a missing polarity or weight). Before anything changes you see what it would add, what it found already there, what it would change and which analyses it would run and record — or why it can't be built. Import makes it one commit. From the command line: `latris build --spec FILE --reuse`, with `--dry-run` for the same preview.

## Practical advice

Generate interpretation sections before relying on them in the report builder. Report mode can show that a section exists but has not yet been generated.
