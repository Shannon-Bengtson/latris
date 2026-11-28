---
title: The Workflow
category: workflow
summary: How the seven stages (Frame, Build, Formalise, Analyse, Interpret, Communicate and Use) and the tracks beside them fit together.
place: project
---

## Stages, steps and tracks

Modelling in Latris moves through seven stages, left to right along the stepper at the top. Each stage has steps, and the same stage and step names are used everywhere: the stepper, the analysis forms, the report's results, the CLI's command index and these help topics. Beside the stages run the **tracks**: work that can happen at any point (AI assistance, evidence, data, review and challenge, verification and validation, versions and history).

## Frame

What the model is for. Write the modelling question, its context and boundary, and who will read the answer (Question and scope, Audience). Then choose the model types to build and record why (Model type selection). Nothing after Frame opens until there is a question.

## Build

The shared map every model type is drawn from. Use Compose to stage candidate factors and links, Visualise to edit the canvas, and Detail to review model elements in table form.

## Formalise

A model type's own content: which elements it has and what kind each is (Definitions), the numbers on them (Values), how uncertain those are (Ranges), and named alternatives (Scenarios). Pick a model type from the Formalise menu; each offers a parameter table, a reference canvas or its own panel.

## Analyse

Results computed from a model and recorded. Analyses are grouped by what they ask, in this order:

- **Structural analysis**: what the model's shape implies, with no values (loops, paths, identification).
- **Base-case analysis**: the model's result from the values as set.
- **Option comparison**: which of the options a person could choose is better.
- **Uncertainty analysis**: how uncertain the result is (Monte Carlo, probabilistic sensitivity analysis).
- **Sensitivity analysis**: which inputs drive the result.
- **Estimation from data**: what a dataset says about an effect.

Each form names its method in its title. Recorded results are listed under the same headings, and the report groups them the same way.

## Interpret

What the results mean: the findings they support, and the written sections (the answer, confidence, limits and open questions). Interpret is per model type: pick one from the Interpret menu. These sections are then available to the report.

## Communicate

The model handed to people who read it. Use the left-hand strip to switch between Report, Diagram, Review, Story and Explorer. Report, Diagram and Review are per model type: assemble report sections, export diagrams, create Word or Markdown reports, and send Review Packs to outside reviewers. Stories belong to the whole project: each tells the answer to the project's question for one audience, drawing on every model type. An Explorer is one model as an interactive page a reader can click through.

**Everything for readers is shared the same way.** Each has *Share by link*: turn it on and you get a link anyone can open, with no account needed. Turn it off and the link stops working; turn it on again and you get a new one. Sharing by link needs the project saved to your Latris account, and only its owner can share. A link always shows the current version of the model. Each also has a download, for a file you can send or keep.

## Use

The model called by code. Declare its contract (the inputs a caller may set, the outputs it returns), try it on your own numbers, and copy the code that runs a pinned version (see "Using a Model Elsewhere").

## Evidence and data

Data and References are always available from the header: they are tracks, not stages. Import datasets and references whenever they are useful; they inform structure in Build and values in Formalise.

## Readiness gates

The stepper shows traffic-light readiness between stages. A red transition blocks progression because required project material is missing. Yellow means work can continue but the output is not yet strong. Green means the project has the expected inputs for that transition.
