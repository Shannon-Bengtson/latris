---
title: Markov Cohort Models
category: model-types
summary: Follow a cohort between states over time, and compare what strategies cost and achieve.
place: frame.model_type
---

## What a Markov model represents

A group of people (a cohort) spread over **states** — Healthy, Sick, Dead — moving between them each **cycle**. Give each factor its element (`latris markov element <factor> state|strategy`); a transition is an ordinary link between two states with a probability per cycle (`latris markov transition "Healthy -> Sick" 0.10 --source registry-2024`). Whatever doesn't leave a state stays in it. Say where the cohort starts (`latris markov start Healthy 1`).

Each state can have a **cost** per cycle and a **utility** — a quality-of-life weight per year, 1 for full health and 0 for dead (`latris markov reward Sick --cost 2500 --utility 0.6`). **Strategies** being compared (Standard care, New drug) use the same model and differ where you override a transition or reward for one of them (`--strategy "New drug"`). Settings set the horizon and cycle length, discounting for costs and outcomes, half-cycle correction, the willingness to pay per unit of outcome and the units (`latris markov settings --cycles 40 --discount 0.035 --wtp 20000 --cost-units £ --outcome-units QALY`).

## What the analysis shows

`latris markov analyse` runs the cohort for each strategy and gives its discounted cost and outcome (e.g. QALYs) per person and the expected time in each state. With two or more strategies it does the standard **incremental analysis**: cheapest first; strategies that cost more and achieve no more are **dominated**; those a mix of their neighbours would beat are **extendedly dominated**; the rest have an **ICER** — the extra cost per extra unit of outcome — against the previous one. Each ICER is the willingness to pay at which the choice changes; with a willingness to pay set, the strategy with the highest net monetary benefit is named.

The result is recorded for the report and goes out of date when any value changes.

## Probabilistic sensitivity analysis and acceptability curves

Every probability, cost and utility is an estimate. Give one a range with `latris markov range`: a transition (`latris markov range "Healthy -> Sick" beta --mean 0.10 --sd 0.02`), a state's cost or utility (`latris markov range Sick gamma --quantity cost --mean 3000 --sd 600`), or all of a state's transitions out as a Dirichlet worth n observations (`--quantity leaving dirichlet --n 200`), so they can't sum past 1. `--strategy "New drug"` puts the range on that strategy's own value. The usual families are beta for probabilities and utilities and gamma for costs, each by the mean and standard error a study reports.

`latris markov psa` samples every range together (seeded Latin hypercube) and reruns the cohort for each sample. It gives each strategy's cost and outcome across the runs (mean, 5th–95th percentile), the incremental analysis on the means (probabilistic ICERs), the **cost-effectiveness acceptability curve** — at each willingness to pay, the probability each strategy is the most cost-effective — and the **expected value of perfect information** per person (the most further research could be worth), with the **partial EVPI** of each input — which single study would be worth most. With a willingness to pay set, it names the strategy to choose, how often it is cost-effective, and which inputs drive its net benefit over the runner-up. Recorded with a chart; it goes out of date when a value or range changes.

## Calling it from a script (contract and predict)

A complete model can have a contract (see **Using a Model Elsewhere**). `latris contract init markov` drafts one: costs and utilities go in, and each strategy's discounted cost and outcome come out, with its ICER and, given a willingness to pay, the best strategy. Transition probabilities, starting shares, time in each state and the cohort's share in each state cycle by cycle (a series) can be added from `latris contract available markov`. Settings that belong to the whole model are named `model` with their cell: `latris contract input markov model --cell markov:discount_rate`. The same goes for the number of cycles and the willingness to pay. A strategy with no ICER, because it is the reference or is dominated, returns nothing and a warning saying why.

## Practical caution

The model is memoryless: the chance of moving depends only on the current state, not on how long someone has been in it. Ranges are sampled independently unless you correlate two of them (`latris markov correlate "Healthy -> Sick" "Healthy -> Sick" 0.8 --other-strategy "New drug"` for two rates from one cohort; `--quantity` / `--other-quantity` for a state's cost or utility); separately sampled probabilities of leaving a state that sum past 1 are scaled down (the report counts the runs — use a Dirichlet to avoid it). The partial EVPI is estimated from the same runs (slightly low; an input whose value can't be told from sampling noise shows as 0 — more runs can reveal a small one); there is no value of sample information (EVSI). Methods: Sonnenberg & Beck (1993), Briggs, Claxton & Sculpher (2006), Drummond et al. (2015), Fenwick, Claxton & Sculpher (2001).
