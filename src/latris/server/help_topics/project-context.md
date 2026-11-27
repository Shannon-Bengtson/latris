---
title: Project Context & Scope Contract
category: getting-started
summary: What the project-level context and scope fields are for and how AI uses them.
place: frame.question
---

## Why project context matters

The project's modelling question is the headline, but on its own it is rarely enough for AI suggestions to land in the right register. Latris reads these foundation fields into every AI prompt:

- **Modelling Question** — the specific question the model exists to answer.
- **Background / Context** — the broader situation: who is this for, what decision does it inform, what is already known, what is the policy or operational setting?
- **Model Boundary** — what is in scope and out of scope.
- **Exclusions** — things deliberately not modelled, with reasons.
- **Predictions** — the behaviour you expect the model to explain (a reference mode), checked against what the AI produces.

Without Background filled in, AI prompts produce generic suggestions ("agricultural trends") instead of mechanistic ones ("phosphorus loading from catchment runoff"). Background is the difference between a textbook answer and a project answer.

## The scope contract (optional, high-leverage)

Three further fields sharpen the *structure* the AI builds. They are optional, but when set they make repeated AI runs cover the same ground at a consistent level of detail — the single biggest lever on model quality and consistency:

- **Coverage Dimensions** — the themes or subsystems the model must span (e.g. "economic, social, environmental drivers"). The AI is told to cover every one, so runs stop drifting to different corners of the problem.
- **Granularity Level** — the intended resolution (e.g. "each node a measurable variable a manager could track" vs "a high-level strategic sketch"). Keeps the abstraction level uniform.
- **Audience** — who the model is for, so variables and mechanisms are framed appropriately.

Leave them blank and the AI uses its judgement; fill them in and the structural prompts treat them as binding.

## What to write

A few sentences is usually enough. Useful elements include:

- The setting: organisation, jurisdiction, or system being modelled.
- The decision the model is meant to inform.
- Stakeholders who will read or act on the model output.
- Constraints, prior work, or upstream context the model should respect.

You can edit Background at any time from the project inspector. Updates are auto-committed and reach all subsequent AI calls immediately.

## How AI uses context

Every prompt that proposes content the user will live with — node descriptions, edge rationales, citation suggestions, evidence-gap detection, interpretation prose — receives these foundation fields as part of its context, and the structural prompts additionally honour the scope contract (coverage dimensions, granularity, audience). You do not need to repeat them in individual prompts; they are threaded automatically.
