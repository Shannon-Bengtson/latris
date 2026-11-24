---
title: The Five-Phase Workflow
category: workflow
summary: How Build, Formalise, Analyse, Interpret, and Communicate & Use fit together.
---

## Evidence basis

Data and References are always available from the header — a persistent resource, not a phase. Import datasets and references whenever they are useful; they inform structure in Build and parameters in Formalise.

## Build

Create the conceptual model. Use Compose to stage candidate nodes and edges, Visualise to edit the canvas, and Detail to review model elements in table form.

## Formalise

Turn the structure into a complete formal model. Select model types, then parameterise each one — a Table representation for the parameter grid (e.g. CLD polarity, FCM weights) and a Canvas representation for reference.

## Analyse

Interrogate a finished model. Pick a model from the Analyse dropdown to see its canvas with overlays (loops, propagation, Markov blanket, d-separation).

## Interpret

Turn analysis outputs and project evidence into structured interpretation sections. Interpret is per-formalism: pick a model from the Interpret dropdown to see that formalism's sections. These sections are then available to the report builder.

## Communicate & Use

The last stage is how the model leaves the workbench: to readers, and to code. Use the left-hand strip to switch between Report, Diagram, Review, Story, Explorer and **Use**. Use is where a model becomes callable from a script: you declare its contract (the inputs a caller may set, the outputs it returns), try it on your own numbers, and copy the code that runs a pinned version (see "Using a Model Elsewhere"). The other five are for readers. Report, Diagram and Review are per-formalism: pick a model from the Communicate dropdown to assemble report sections, export diagrams, create Word or Markdown reports, and send Review Packs to outside reviewers. Stories belong to the whole project: each tells the answer to the project's question for one audience, drawing on every model type. An Explorer is one model as an interactive page a reader can click through.

**Everything for readers is shared the same way.** Each of those five has *Share by link*: turn it on and you get a link anyone can open, with no account needed. Turn it off and the link stops working; turn it on again and you get a new one. Sharing by link needs the project saved to your Latris account, and only its owner can share. A link always shows the current version of the model. Each also has a download, for a file you can send or keep.

## Readiness gates

The stepper shows traffic-light readiness between phases. A red transition blocks progression because required project material is missing. Yellow means work can continue but the output is not yet strong. Green means the project has the expected inputs for that transition.
