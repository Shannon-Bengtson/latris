---
title: Sharing & Syncing Projects
category: collaboration
summary: Your projects and workspaces (teams, admins and members, folders), managing a project, inviting collaborators, and publishing versions.
place: project
---

## Where collaboration lives

Open the **Versions** view (top-right). Everything about working with other people lives here, alongside the version tree — there is no separate sync screen.

## Sharing a project

In the Versions view, under **People**, enter a name and click **Share**. Latris creates a private online copy of the project. From then on you choose which versions collaborators can see.

## Your projects

After you sign in, **Your projects** lists your projects, with your role on each. **Open** starts working in it. **New project** names a new one, in the workspace you are looking at, and opens it.

Each project's **⋯** menu offers what your role allows ("owner" below also means an admin of the project's workspace):

- **People…** — who is on the project. The owner invites by email, changes roles, removes people, and can **transfer ownership** to someone who has joined (the old owner stays on as a collaborator).
- **Rename…** (owner) — changes the name only; its shared links don't change.
- **Move to folder…** (owner) — files it in one of the workspace's folders, or takes it out.
- **Move to workspace…** (owner) — moves it to another workspace you are in. The people on it stay on it; the admins of the workspace it leaves stop seeing it, and the admins of the one it joins start.
- **Archive** (owner) — moves the project to **Archived**, below the list, out of the way. An archived project can't be opened, or edited from a chat, until you **Restore** it; its report and shared links keep working. Anyone working in it is closed out (their last changes are saved).
- **Move to trash…** (owner) — hides the project from everyone but its owner and its workspace's admins, closes out anyone working in it, and stops its report and shared links. It waits in **Trash** for **30 days**: **Restore** brings it back as it was, links and all. After 30 days it is deleted for good.
- **Leave project…** (anyone but the owner) — takes you off the project. The owner can add you again. An owner who wants to leave transfers ownership first.

On a phone the list shows each open project's report; manage projects from a computer.

## Workspaces

Every project belongs to a **workspace**. The picker at the top of Your projects chooses which one you are looking at:

- **Personal** — yours alone. Share a project from here by adding people to that project.
- A **team workspace** — for a team's projects. Start one with **＋ New team workspace…**.
- **Shared with me** — projects you were added to in a workspace you aren't in.

In a team workspace there are two roles:

- An **admin** sees and manages **every** project in the workspace, whether or not they were added to it, and manages who is in the workspace. A project an admin isn't on shows who owns it.
- A **member** can start projects in the workspace and sees **only the projects they are added to**. Being in the workspace does not show them anyone else's.

**Workspace settings** (beside the picker) is where an admin renames the workspace, adds people by email as admin or member, changes roles, removes people, and keeps its **folders**; projects are grouped by folder on the page. Removing someone takes them off the workspace's projects, and the projects they own pass to the admin who removed them. Anyone can **leave** a team workspace, except its only admin, and except while they still own projects there (transfer or move those first). An empty team workspace can be deleted.

Transferring a project from your Personal workspace to someone else moves it to *their* Personal workspace. In a team workspace it stays where it is.

## Keeping in sync (turn-based, per version)

Modelling is deliberative, so collaboration is **turn-based**, not live, and it works **one version at a time**:

- **Publish** a version to make it visible to the project.
- **Get latest** on a version when the shared copy has moved ahead (the version shows an "Updates" badge).
- A version a collaborator published that you don't have yet shows as a faint **ghost** — click it to **add it to your workspace**.

Each version on the tree shows its state at a glance (Local, Shared, changes to publish, Updates, or Diverged). Coordinate with collaborators so you're not editing the same version at once.

## Members and roles

The project owner manages who can access a shared project:

- **Owner** — controls membership, renames, files, moves, archives and can move the project to the trash. An admin of the project's workspace can do the same.
- **Collaborator** — can change the model.

Invite someone by **email** from **People** (in a project's **⋯** menu on Your projects, or in the Versions view). They get an account the first time they sign in, then the project appears in their list. (Until you publish a version, a collaborator who opens the project sees nothing yet.)

## Report link

Under **People**, the owner can turn on a **report link**: a read-only web page of the project's report (with its diagram) that anyone with the link can open — no account needed, and it isn't indexed by search engines. Pick which report pack it shows; the page has a contents list beside it (at the top on a phone). It's off by default. Turning it off and on again issues a new link, so an old one stops working.

## Models made in a chat

If you build a model with an AI chat (using the Latris connector), it starts **unsaved** and expires 30 days after its last edit. Ask the AI to save it: it gives you a one-time link that adds the model to your account (sign in with just your email). Saved models appear in your project list, and the chat can keep editing them.

## Reconciling a diverged version

If you and a collaborator both change the **same version** before sharing, it **diverges** — the version shows a "Diverged" badge. Click **Reconcile** to see what changed on the shared copy side by side, then **keep one line**. The line you don't keep is preserved as an **archived** version (turn on "Show archived versions" to see it) — nothing is ever deleted. Coordinate with the other person so divergence stays rare.

## One server per project

A shared project remembers which server it belongs to. Don't share the same project against two different servers (e.g. a local test server and the hosted one) — that crosses wires and sync will fail.
