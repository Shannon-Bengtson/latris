---
title: Lineage and Versioning
category: versioning
summary: Use milestones and alternatives to compare model histories without losing auditability.
---

## What lineage is for

Lineage tracks named versions, milestones, and alternatives in a Git-backed project. It lets you preserve model history while exploring different assumptions or framings.

## Main concepts

- **Milestone:** a named checkpoint on the current branch.
- **Alternative:** a new version branch from a milestone or current state.
- **Current version:** the branch or lineage node currently being edited.

## Comparing versions

**Compare with…** in the versions panel lists what changed between the version you're on and another version or a model checkpoint — factors and links added, changed and removed, and the rest of the record (sources, assumptions, decisions) — naming each factor and link. **Show on the canvas** marks what was added and changed on the model; what was removed is listed, since it isn't there to mark. From the command line: `latris version compare <from> <to>`, where either side is a version or a checkpoint.

## When to branch — and when to use a scenario instead

Create alternatives when a modelling assumption, framing, or stakeholder view would change the structure enough that simple notes are not enough: a different link, equation or mechanism; a competing expert view.

Don't branch for options you want to compare (a policy, a delayed start, a high-load world). Those are **scenarios** in one version: they share the same model and the same uncertainty draws, so their differences are paired and a fix to the model reaches every option at once. A useful rule: scenarios answer *what could we do?*; alternative versions answer *what do we believe about how the system works?*

## Published vs local versions

When a project is shared with collaborators, each version is either **local** (only on your machine) or **published** (visible to everyone on the project). Explorations stay local until you choose to **Publish** them, so half-formed what-ifs are not shared by accident. Each version on the tree shows its state at a glance:

- **🔒 Local** — only you have it; publish it to share.
- **✓ Shared** — in sync with the project.
- **⬆ N to publish** — you have changes the project has not seen yet.
- **⬇ Updates** — the shared copy has changes; use **Get latest**.
- **👻 Ghost** — a version a collaborator published that is not in your workspace yet; **add it** to bring it in.

These replace any notion of "push" and "pull" — you publish a version and get the latest for a version; the version tree is where collaboration lives.

## Audit value

Reports can include milestone history so reviewers can see how the model evolved, not only the final result.
