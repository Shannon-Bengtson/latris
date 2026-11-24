---
title: Explorer (interactive model)
category: communicate
summary: Hand someone the model itself, as a page they can click through, with the reasoning and sources behind it.
---

## What an Explorer is

An Explorer is one of your models as an interactive web page. A Story tells the reader what the model says; an Explorer lets them look for themselves. It works for every model type.

On the page a reader can:

- **Hover** over a factor or a link for a summary, and see what it connects to.
- **Click** anything for its description, why it is there, how confident the model is in it, whether a person has reviewed it, and what supports it.
- **Trace** what drives a factor and what it drives. Where links have a direction, they can follow a change: if this goes up, what goes up, what goes down, and what depends on how strong the links are.
- **Light up a feedback loop** from the list of loops.
- **Highlight** the links with no source yet, the disputed ones, and anything proposed by AI that nobody has reviewed.
- **Read the results** the model has recorded, as charts and tables.

## Trying things on a Bayesian network

When the model is a Bayesian network and the page carries *Everything*, a reader can also work the model:

- **Click a state** to say it has been seen. Every factor's probabilities update at once, with a mark showing where each stood before.
- Choose **We see this** (an observation, which also tells you about its causes) or **We make it so** (an intervention: what follows responds, its causes stay as they were).
- Say **how sure** they are of an observation, from 50% to 100%.
- Switch between the model's saved **options** and see what each changes.
- Keep one factor **in view**, and see **what to find out next**: the other factors ranked by how much knowing them would tell you about it.
- See **the most likely explanation**: the single most likely state of everything at once.

The numbers are calculated in the page from the model's own probability tables, and give the same answers as Latris itself. The page opens where the model's latest recorded query stands.

## Trying values on a simulation

When the model is a system-dynamics model and the page carries *Everything*, a reader can run it themselves:

- **Move a value.** Every constant has a slider, over the range you gave it as its uncertainty (or half to one and a half times its value if you gave none). So does each stock's starting value. The graph redraws as they drag.
- **Read the graph.** Any stock, flow or variable over time, with the model as you built it as a dashed line behind it, and where it ends up compared with that. It opens on the model's outcome.
- Switch between the model's saved **scenarios**, and carry on from one.
- **Put it back**, one value or all of them.

The page simulates from the model's own equations, and is tested against Latris's own runs.

## Trying things on the other model types

At *Everything*, these also recalculate in the page as the reader changes something, each shown against the model as you built it:

- **Multi-criteria analysis**: move how much a criterion counts. The others keep their proportions, the options are re-ranked, and marks on each slider show where the top choice would change.
- **Fuzzy cognitive map**: hold a factor at a level and see what moves.
- **Decision tree**: change the odds, a payoff or a cost along the way, and see the best choice and the plan that follows.
- **Event tree**: change the odds at a step, or how often it starts, and see how it ends.
- **Competing hypotheses**: set a piece of evidence aside and see which hypothesis leads, and which evidence the lead rests on.
- **Fault tree**: change how likely a basic event is, from never to certain, and see the top event, what drives it and the ways it can happen.
- **Bow-tie**: change how often a barrier fails or a threat arises, and see how often the top event and each consequence follow.
- **Markov cohort model**: change a chance of moving, a state's cost or quality of life, or what an outcome is worth paying, and see each strategy's cost and outcome and which is the best value.
- **Causal DAG**: pick a cause and an effect, tick what to adjust for, and see which paths between them are open, whether the effect can be read cleanly, and the smallest sets of factors that would make it so.
- **Theory of change**: follow a pathway from activity to impact link by link, with what holds each link up, and suppose a link fails to see what no longer follows.

A causal loop diagram has no numbers to change: its page has the loops, tracing, reasoning and sources.
- **Copy a link to what they are looking at**, so a colleague opens the same view.

## Making one

1. In Communicate, choose **Explorer** and **New explorer**. It is made for the model you have open.
2. Try it in the preview: it is exactly the page your readers get.
3. Give it a heading and a line or two on what to look for.
4. **Share it by link**, or **download the page**. The link opens the explorer for anyone who has it, with no account needed, and always shows the current model. The download is one file that works offline: send it to colleagues or put it on your own website.

## What leaves the building

You decide what the page carries:

- **Structure**: the picture, descriptions, confidence and review status.
- **Results**: also the model's recorded results.
- **Everything** (the default): also the model's own numbers, so readers can try their own what-ifs where the model type supports it. Anyone who has the file can read those numbers, so choose a lower level for a confidential model.

**Show sources** is on by default: readers see what each link cites, whether the source was checked, and the passage that was quoted. The text you stored from a source never leaves.

## A snapshot

The page is stamped with the date it was made and the version of the model it came from. A downloaded file does not change when the model does: download it again after you update the model. A shared link redraws itself from the current model.

Explorers are made in the Latris app.
