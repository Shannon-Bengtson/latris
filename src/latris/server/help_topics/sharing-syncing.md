---
title: Sharing & Syncing Projects
category: collaboration
summary: Share a project online, invite collaborators by email, and publish versions so others can see them.
---

## Where collaboration lives

Open the **Versions** view (top-right). Everything about working with other people lives here, alongside the version tree — there is no separate sync screen.

## Sharing a project

In the Versions view, under **People**, enter a name and click **Share**. Latris creates a private online copy of the project. From then on you choose which versions collaborators can see.

## The project list

The landing page shows all your projects in one list, each with a status:

- **Local** — exists only on this machine; not shared.
- **Synced** — your local copy is linked to an online project. Open it as usual.
- **Available** — a project shared *with you* online that you haven't downloaded yet. Click it to clone a local copy, then it becomes Synced.

The list is deduplicated: a project that is both local and online shows as **one** row, not two.

## Keeping in sync (turn-based, per version)

Modelling is deliberative, so collaboration is **turn-based**, not live, and it works **one version at a time**:

- **Publish** a version to make it visible to the project.
- **Get latest** on a version when the shared copy has moved ahead (the version shows an "Updates" badge).
- A version a collaborator published that you don't have yet shows as a faint **ghost** — click it to **add it to your workspace**.

Each version on the tree shows its state at a glance (Local, Shared, changes to publish, Updates, or Diverged). Coordinate with collaborators so you're not editing the same version at once.

## Members and roles

The project owner manages who can access a shared project:

- **Owner** — controls membership and can delete the project.
- **Collaborator** — can change the model.

Invite someone by **email** from **People** in the Versions view. They get an account the first time they sign in, then the project appears as **Available** for them to open. (Until you publish a version, a collaborator who opens the project sees nothing yet.)

## Report link

Under **People**, the owner can turn on a **report link**: a read-only web page of the project's report (with its diagram) that anyone with the link can open — no account needed, and it isn't indexed by search engines. Pick which report pack it shows; the page has a contents list beside it (at the top on a phone). It's off by default. Turning it off and on again issues a new link, so an old one stops working.

## Models made in a chat

If you build a model with an AI chat (using the Latris connector), it starts **unsaved** and expires 30 days after its last edit. Ask the AI to save it: it gives you a one-time link that adds the model to your account (sign in with just your email). Saved models appear in your project list, and the chat can keep editing them.

## Reconciling a diverged version

If you and a collaborator both change the **same version** before sharing, it **diverges** — the version shows a "Diverged" badge. Click **Reconcile** to see what changed on the shared copy side by side, then **keep one line**. The line you don't keep is preserved as an **archived** version (turn on "Show archived versions" to see it) — nothing is ever deleted. Coordinate with the other person so divergence stays rare.

## One server per project

A shared project remembers which server it belongs to. Don't share the same project against two different servers (e.g. a local test server and the hosted one) — that crosses wires and sync will fail.
