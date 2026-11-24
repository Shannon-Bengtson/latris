---
title: Decision Trees
category: model-types
summary: Find the best choice under uncertainty, and what finding out more first would be worth.
---

## What a decision tree represents

**Decision** nodes where someone chooses, **chance** nodes where the world does, and **terminal** nodes with a payoff. Give each factor its type (`latris dt element <factor> decision|chance|terminal`) and link each node to its children with ordinary links; each node has one parent, so repeat an outcome under each branch rather than sharing it. Then set each branch's label and, from a chance node, its probability (`latris dt branch "Demand if launched -> High demand, launched" --label High -p 0.4`), any value along a branch such as the cost of a test (`--value -20`), each terminal's payoff (`latris dt payoff <terminal> 500 --source forecast`), and whether you're maximising (profit) or minimising (cost) (`latris dt settings --objective maximise --units "$k"`).

When the same uncertainty appears under several choices — demand if you launch, demand if you license — give those chance nodes one name (`latris dt uncertainty <chance node> Demand`) with the same states and probabilities, so the tree can price knowing it.

## What the analysis shows

`latris dt analyse` rolls the tree back — a chance node is worth the probability-weighted value of its branches, a decision node the best of its options — and gives:

- the **best strategy** and the expected value of each first choice;
- the **expected value of perfect information** for each uncertainty — the most it's worth paying to know it before choosing (market research costing more isn't worth it) — and for all of them together;
- for each two-state uncertainty, the **probability at which the best choice changes**;
- the values on the best path nobody has verified.

The result is recorded for the report and goes out of date when the tree or a value changes.

## How sure is the choice? (probabilistic sensitivity analysis)

Give uncertain inputs a range with `latris dt range`: a terminal's payoff (`latris dt range "Launched, high demand" normal --mean 500 --sd 100`), a branch's value (`--quantity value`), the probability of one branch of a two-branch chance node (`latris dt range "Demand if launched -> Launched, high demand" beta --mean 0.4 --sd 0.1` — the other branch takes the rest), or every branch probability of a chance node as a Dirichlet worth n observations (`latris dt range "Demand if launched" dirichlet --n 50`). A beta (probabilities) or gamma (costs) takes the mean and standard error a study reports; uniform, triangular, normal and lognormal take their own parameters. Each range keeps its reason, source and whether a person checked it, and must include the current value. Chance nodes named as one uncertainty take the same sampled probabilities.

`latris dt psa` then samples every range together (seeded Latin hypercube) and rolls the tree back for each sample: each first choice's expected value across the runs (mean, 5th–95th percentile), **how often each option is best**, the **expected value of perfect information on the parameters** — the most it's worth to remove all of this uncertainty before choosing — the **partial EVPI** of each input on its own (what one study of it could at most be worth), and which inputs drive the advantage of the best option over the runner-up (rank correlation). Inputs without a range are held fixed and listed. Two values from the same source can be sampled together: `latris dt correlate "Launched, high demand" "Launched, low demand" 0.6 --reason "one finance model"` (a rank correlation, -0.99 to 0.99; each keeps its own range). It is recorded with a chart, and goes out of date when a value or range changes.

## Practical caution

Expected value is risk-neutral: a strategy with a small chance of ruin can still come out best. Probabilities and payoffs are point values unless given a range, and ranges are sampled independently. Perfect information is an upper bound — real research is imperfect and worth less. Methods: Raiffa (1968), Clemen & Reilly (2014), Howard (1966).
