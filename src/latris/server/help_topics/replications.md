---
title: Replications: Checking Latris Against Textbook Models
category: developer
summary: Textbook models rebuilt in Latris, each with the results it must reproduce, so you can check the engines for yourself.
place: project
---

## What they are

A replication is a well-known model from the literature, rebuilt in Latris from a build spec that cites the original, together with the numbers it must reproduce. They ship with Latris, so anyone can rerun them:

- **Asia chest clinic** (Bayesian network, Lauritzen & Spiegelhalter 1988): marginal probabilities, and the updated chances of each disease once a visit to Asia and shortness of breath are observed.
- **Bass diffusion** (system dynamics, Bass 1969): the adoption curve, its peak and when it comes, against the model's exact solution.
- **SIR epidemic** (system dynamics, Kermack & McKendrick 1927): the epidemic's final size and peak, against the exact values the equations imply.
- **Pearl's back-door example** (DAG, Pearl 2009): which adjustment sets are sufficient, and every minimal one.
- **Senge's system archetypes** (causal loop diagram, Senge 1990): limits to growth and fixes that fail, each loop found and classified.

## Running them

```bash
latris replicate list                    # what ships
latris replicate check                   # build each, run its analyses, compare
latris replicate check asia --keep out/  # one, keeping the project it builds
latris replicate build asia asia-model   # a project of your own to inspect or report on
```

They work outside a project. Each build commits to git, so a git identity must be set. `check` exits 1 if any result differs from what is expected.

## Reading the results

Each check shows the expected value, what Latris computed, and its **basis**: where the expected value comes from.

- **published**: a number or answer printed in the original work (the check names the table, figure or section).
- **closed form**: a formula the model satisfies exactly, such as the Bass model's solution.
- **exact**: an exact calculation from the published inputs, done without Latris (the test suite repeats it independently).

A check also records whether a person has compared its expected value with the original. Until someone has, treat it as you would any unverified source.
