---
title: AI Assistance
category: ai
summary: How Latris uses AI for proposals, review, citations, interpretation, and report drafting.
---

## AI role

AI in Latris is a drafting and review assistant. It can propose model structure, citations, challenges, evidence gaps, peer-review comments, interpretation prose, and report sections.

## Review contract

AI output should pass through preview and approval before it changes project state. Accepted AI contributions are recorded so later reviewers can see where AI was involved.

## Bring your own key

The backend uses a provider-agnostic AI layer. API keys are managed outside the project content and are not committed into the model.

## Good use cases

- Draft candidate nodes and edges.
- Suggest missing connections.
- Challenge a relationship.
- Suggest citations for a claim.
- Identify evidence gaps.
- Draft interpretation prose from accepted findings.

## Human responsibility

The modeller remains responsible for accepting, editing, or rejecting proposals. Treat AI as a source of candidate work, not as an authority.

## AI agents using the command line

When an AI agent (such as Claude Code) runs `latris` commands, Latris recognises it and records what it adds as AI-proposed. Each change it saves notes the agent. Approvals, reviews, sign-offs and resolved challenges are a person's judgement: the agent records one only when you have reviewed the item yourself and asked it to, and the change history says it was recorded on your instruction. This catches the ordinary case; it can't stop an agent that sets out to hide itself. Approve in the Latris app when you need an approval that only you could have made.
