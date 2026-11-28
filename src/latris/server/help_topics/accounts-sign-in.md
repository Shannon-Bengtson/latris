---
title: Accounts & Signing In
category: collaboration
summary: Passwordless sign-in, creating an account, your profile, connected chat apps, and signing out.
place: project
---

## Passwordless sign-in

Latris uses **magic-link** sign-in — there is no password. You enter your email, Latris sends you a one-time code, and you type that code in. The code expires after ten minutes; request a new one if it lapses.

## Sign in vs Create account

The sign-in screen has two tabs:

- **Sign in** — for an email that already has an account.
- **Create account** — for a new account. You provide your **first and last name** (required) and **organisation** (optional) before requesting your code.

If you pick the wrong one, Latris tells you (e.g. "No account for this email — choose Create account") so you can switch.

## Your profile and authorship

- Your **name** and **email** appear as the author on the model changes you make (this is part of the project's provenance and travels with the model).
- Your **organisation** stays on your account only — it is **not** written into the shared model.
- Open the **account menu** from your name in the top-right to **Edit profile**, see **Connected apps**, or **Sign out**. (This is separate from the **Versions** view, where sharing and collaboration live.)

## Connected apps

You can sign in to Latris from an AI chat app such as Claude or ChatGPT, so it can save models to your account and open the ones you have there. You sign in on a Latris page with your emailed code and choose whether to allow the chat app.

- A connected chat app can see and change the models **you own**. Its changes are recorded under your name, as AI-proposed until you review them.
- What you open from the chat is sent to that chat app's AI provider.
- **Account menu → Connected apps** lists each chat app you allowed, where it sends you back to, and when it was last used. **Disconnect** ends its access straight away; sign in from the chat app again to reconnect.
- A model saved to your account can't be changed from a chat by its old link token alone: the chat needs your sign-in.

## Which server

Accounts live on a Latris **sync server**. Most people never change it — it's prefilled. If you need to point at a specific server, expand **Advanced** on the sign-in screen. Once you sign in successfully, the app remembers it.

## Invite-only

A server may be **invite-only**: an administrator allows specific emails. If your email isn't approved you won't be able to create an account on that server.
