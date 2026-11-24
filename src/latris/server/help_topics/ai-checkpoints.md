---
title: When the AI asks you
category: ai
summary: Five checkpoints where an AI building a model stops and asks the person, and how skips show in the report.
---

## Why it asks

An AI building a model for you — in a chat with the Latris connector, or running `latris` commands — knows the sources but not your situation. So at each phase of the workflow it stops at a **checkpoint** and asks you a few specific questions, built from the model it has so far:

1. **Framing** (before building) — what's happening and the decision the model informs, who will read it, and what you expect the answer to be.
2. **Structure** (Build → Formalise) — the factors it has mapped: is anything missing, which of them can you change, and is its least-supported link right?
3. **Values** (Formalise → Analyse) — the few estimates the answer depends on most (found by sensitivity analysis): are they right?
4. **Surprise** (Analyse → Interpret) — the result next to what you expected: does it match what you see?
5. **Audience** (Interpret → Communicate) — the reader the report is for, and what they'll push back on.

At most three questions at a time. Nothing is blocked: the AI can carry on without you, but only by saying so.

## What gets recorded

Your answers are recorded in your words, with the agent that relayed them (`latris checkpoint record`). If you tell the AI to carry on alone, it records the skip and why (`latris checkpoint skip`), or — if you say "just build" — stops asking for the rest of the model (`latris checkpoint pace just-build`). Answers are not a sign-off; approving the model is a separate step.

The report's **What the person reviewed** section lists each checkpoint: what you said, what was skipped and why, and what was never asked. A reader can tell a model you shaped from one the AI built alone.

## When it applies

Only to models an AI built: when most factors were added by a person, no checkpoint opens. A person at a terminal isn't prompted; `latris checkpoint show` lists the checkpoints and the one open now. A reviewed structure opens again if the AI later grows the map a lot.
