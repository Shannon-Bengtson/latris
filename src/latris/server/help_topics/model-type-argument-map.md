---
title: Argument Maps
category: model-types
summary: Lay out an argument and see whether its conclusion stands, and what it rests on.
place: frame.model_type
---

## What an argument map represents

A **conclusion** — what is being argued for — and the **claims** offered for and against it. Give each factor its element (`latris argument element <factor> conclusion|claim|question`; a question is the issue the conclusion answers). A link from a premise to the claim it bears on is an ordinary link (`latris edge add "Premise" "Claim"`); say how it bears with `latris argument link "Premise -> Claim"`:

- `--relation supports` (the default) or `attacks` — an objection. An objection to an objection is an answer to it (a rebuttal): it attacks the objection.
- `--reason NAME` — premises that only work together ("it works *and* we can afford it") share a reason name; a premise with no reason name is a reason on its own.
- `--warrant` — why the premise bears on the claim; `--qualifier certainly|probably|possibly` — how strongly the arguer says it does.

A claim's **grounds** are its ordinary sources: `latris evidence add <claim> description <key>`, then `latris evidence check` once read. To object to an **inference** rather than a premise ("even if that's true, it doesn't follow"), open a challenge on the link: `latris challenge open "Premise -> Claim" "…"` — the reason counts for nothing until the challenge is resolved. A person can accept or reject a premise the map doesn't argue further: `latris argument claim <claim> rejected --rationale "…"`.

## What the analysis shows

`latris argument analyse` labels every claim (grounded labelling, Dung 1995): it **stands** when every objection to it is defeated and a reason for it holds — or it is a premise taken as given (not argued further, not rejected, and its sources don't dispute it); it is **defeated** when an objection to it stands or every reason offered for it fails; otherwise it is **undecided** (a premise whose source disputes it, or two claims attacking each other). Then:

- whether the **conclusion stands**, and the reasons it stands on;
- **unanswered objections** — those still standing, anywhere under the conclusion;
- **linchpins** — premises whose rejection alone would stop the conclusion standing, with whether their sources are checked;
- what the premises rest on: checked sources, unchecked ones, a person's acceptance, or nothing — so "it stands" never hides "it stands on assertion";
- reasons with no warrant, and inferences under challenge.

The result is recorded for the report with a diagram, and goes out of date when the map, a source or a challenge changes.

## Practical caution

The evaluation is qualitative: qualifiers are reported, not weighed, and one strong reason counts as much as several weak ones. A premise you don't argue further stands by default — that is what the report's "no source" list is for. Methods: Toulmin (1958), Kunz & Rittel (1970), Dung (1995), Cayrol & Lagasquie-Schiex (2005), Pollock (1987).
