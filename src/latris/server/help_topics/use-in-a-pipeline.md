---
title: Using a Model Elsewhere (Contract and Predict)
category: communicate
summary: Declare a model's inputs and outputs, then run it from a script on a version you pin.
---

## What this is for

A model you have built and argued for can be used outside Latris: in a script, a notebook, a scheduled job. Two things make that safe.

- A **contract** says which of the model's values a caller may set (its inputs) and which results it returns (its outputs), under names that don't change when a factor is renamed.
- **Predict** runs the model on the values a caller gives and returns the outputs. Nothing is recorded in the project.

Every model type that computes something from inputs can have a contract: equation models, system dynamics, Bayesian networks, fuzzy cognitive maps, fault trees, bow-ties, event trees, decision trees, Markov models and MCDA. Theories of change, argument maps, analyses of competing hypotheses and loop maps don't compute anything, so they have none.

## Declaring the contract

`latris contract init equation_model` drafts one from the model: what the model treats as given goes in, what it is for comes out. Then prune it. Every input is a promise to whoever calls the model, so expose only what a caller should set.

- `latris contract available <model type>` lists everything the model could expose.
- `latris contract input <model type> <factor> --name depth --min 0.2 --max 3` adds or changes an input: its name, units, default and valid range. For a Bayesian network an input is a factor's state, observed (`--observe`) or made so (`--set`).
- Some factors hold several things a caller could set: a bow-tie barrier has a failure probability and a status, and an event-tree heading has a probability on each branch. Each one is named by its **cell** (listed by `contract available`): `latris contract input bow_tie "Gas detection" --cell bow_tie:status`. What belongs to the whole model rather than one factor, such as a Markov model's discount rate, is named `model`: `latris contract input markov model --cell markov:discount_rate`.
- `latris contract output <model type> <factor>` adds an output. A system dynamics variable can be returned as its whole run (`--kind series`) or as one value of it (`--metric final`, `peak`, `mean`…).
- `latris contract show` prints the contract; `latris contract check` says whether it still fits the model.
- An output keeps the units the contract promised: if the model's own units change later, `predict` converts the result to the contract's units, and `contract check` says so when they can no longer be converted. An input or output name can stand for only one factor.

## Running it

`latris predict --set depth=2.5` runs the model once. An input you leave out takes its default, or the model's own value. The result gives:

- the **outputs**, with units. A *choice* output (a decision tree's best option, an MCDA's top option) is the option's name;
- the **inputs** it used, and where each came from;
- **warnings**: a value outside its valid range is used as given, and the result is flagged as an extrapolation. A value the model can't take at all, such as a probability above 1, is refused;
- **provenance**: the commit that produced it, the contract's hash, and the review state of that version.

This is different from an analysis. An analysis (a simulation, a query, an evaluation) is recorded for the report. A prediction is a call: make as many as you like.

## Pinning a version

`latris predict --ref "Signed off"` runs the model exactly as it was at that milestone, whatever has changed since. `--ref` takes a milestone's name, a version's name or a commit. Predict never refuses an unreviewed version: it reports the review state. A pipeline that wants a gate adds `--require approved`.

From Python:

```
import latris
model = latris.load("path/to/project", ref="Signed off")
result = model.predict({"depth": 2.5})
```

## Moving to a newer version

`latris contract diff "Signed off"` compares that version's contract with the latest:

- **Breaking**: an input or output was removed or renamed, now stands for a different factor, its units changed, or an input became required. A caller written against the old version may fail.
- **Compatible**: something optional was added, or a default or range changed. The caller still works.
- **Internal only**: the contract is the same but the model behind it changed, so the same inputs may give different outputs.

## In the app

**Communicate & Use → Use** (the last button on the left strip) shows the contract for the model you have open. **Draft the contract** fills it from the model; the tables set each input's default and valid range and add or remove inputs and outputs. **Try it** runs the model on values you type and shows the outputs, any warnings and the commit they came from. The pane on the right gives the Python and command-line code for a pipeline. Choose a milestone there to pin the code to it and to see whether the model as it is now would break a caller written against that milestone.

## Practical caution

Units the unit library doesn't know (a currency such as GBP, or QALY) are kept exactly as written: a value in them is never converted, and a value in different units is refused.

A contract doesn't make a model right for a use it wasn't built for. State valid ranges honestly: they are how a caller learns that it has left the ground the evidence covers. Time-series inputs aren't supported yet; a caller who needs one loops over single values.
