---
title: System Dynamics (stock-and-flow)
category: model-types
summary: Stocks, flows, unit-checked equations, scenarios, Monte Carlo uncertainty, sensitivity and loop dominance — with per-parameter provenance.
place: frame.model_type
---

## What an SD model adds

System Dynamics models how quantities accumulate and drain over time. **Stocks** (population, inventory, pollutant load) change only through **flows** (births, orders, emissions); flows and **auxiliaries** are computed from equations; **constants** are fixed parameters; a **source_sink** is a cloud outside the model boundary. Simulating integrates the model forward in time, so you can see growth, overshoot, oscillation, or collapse emerge from the feedback structure.

## How it sits on the substrate

SD uses the same entities and edges as every other view. Each SD variable is an ordinary entity with an SD **role**. Material movement uses **flow** edges, always `stock → flow → stock` (either end may be a source_sink cloud). "X appears in Y's equation" uses a **causal** edge X → Y — an information link. The SD model is whatever has an SD role plus anything a flow edge touches.

**Sharing a map with a loop map.** A factor joins the simulation when it gets an SD role (and the network when it gets states); everything else stays in the loop map. So you can quantify part of a CLD *in place*: give its key factors roles, and links from the rest of the loop map into them stay loop-map links — `sd check` lists them as advisories ("stays in the loop map"), never as gaps. In a model shared with a loop map, a causal link into a stock or one no equation uses is likewise an advisory. `sd unset-role <node>` takes a factor back out (its role and SD values go; the factor, its links and citations stay). In a model that is only a simulation, an unclassified factor feeding it is still a gap. The factor the model explains is set with `latris view role sd <factor> outcome` (kept with the SD settings, since SD roles are one per factor) and `latris sd simulate` runs it.

## Equations and units

Equations reference variables by slugified label (`Birth Rate` → `birth_rate`) plus `TIME`, using arithmetic, comparisons, and `MIN`, `MAX`, `ABS`, `IF_THEN_ELSE(cond, a, b)`, `STEP(height, start)`, `RAMP(slope, start[, end])`, `PULSE(start, width)`, `TABLE(x)`, `EXP`, `LN`, `SQRT`, `SIN`, `COS`, `MODULO(x, period)` (plus `PI`), and the delays `SMOOTH(x, T)` / `SMOOTH3` (a perceived value catching up with x) and `DELAY1(x, T)` / `DELAY3` (material arriving after a delay) — each becomes hidden stocks and flows, so units, Monte Carlo and loop dominance include them. A bare start, end, width or delay time is in the model's time units. **Seasons**: a yearly model can still have a seasonal cycle — set a step shorter than the cycle (`sd set-settings --dt 0.02` is about weekly) and drive it with `1 + amplitude * SIN(2 * PI * TIME / one_year)` (`one_year` a constant of 1 year), or a lookup over `MODULO(TIME, one_year)` (the time within each year). Every stock, constant and equation declares its **units** (pint syntax: `liter`, `person/year`, `1/year`, `dimensionless`; `person`, `dollar` and `item` are built in). Values are evaluated as unit-bearing quantities, so adding litres to people, or a flow whose units aren't its stock's units per time unit, is caught as an error rather than producing a wrong number. Equations have no unit literals — give a unit-bearing number its own named, sourced constant. An equation that is just a bare number (`3`) takes its declared units.

## Building the model (the `sd` commands)

Each is `latris sd …` on the command line (e.g. `latris sd check`, `latris sd simulate --scenario NAME`); the chat connector and the editor call the same operations.
- **`sd set-role <node> <role>`** — stock, flow, auxiliary, constant, or source_sink.
- **`sd set-settings --time-units month --final-time 36`** — the model's clock and run settings, stored with it (every run, and anyone opening a link, uses them; options on a run override). If the flows are per month but the clock runs in years, every run and `sd check` warn. **`latris view role sd <node> outcome`** marks what the model explains.
- **`sd set-initial-value <stock> <value> --units …`** — a stock's starting value (`--non-negative` warns if a run drives it below zero).
- **`sd set-constant <node> <value> --units …`** and **`sd set-equation <flow|aux> "<expr>" --units …`** — each with `--origin`/`--source` provenance.
- **`sd set-table <node> -p x:y -p x:y … --x-units … --y-units …`** — a piecewise-linear lookup the node's equation calls as `TABLE(x)`; typically elicited from experts as a curve.
- **`sd check`** — readiness: classification, stock-flow plumbing, no algebraic loops among flows/auxiliaries, equations match the diagram's links (no hidden or unused dependencies), values and tables present, and full dimensional consistency.
- **`sd set-scenario NAME --set "Variable=value [units]" …`** — a named what-if saved with the model, with `--description`, `--reason`, `--source`. Values replace constants or initial values and are unit-checked (a delay in years can be set as `6 month`, not `6 person`). `--extends OTHER` builds on another saved scenario: its values apply first and this one's on top, so "Programme delayed 1 year" can extend "Programme" and change only the start year. `sd scenarios`, `sd remove-scenario` (a scenario others extend can't be removed until they are).
- **`sd set-uncertainty <node> <distribution> …`** — how uncertain a constant or initial value is, in its own units: uniform (`--min --max`), triangular (`--min --mode --max`), normal/lognormal (`--mean --sd`, optional `--min/--max` truncation), beta (`--alpha --beta`, scaled to min..max), gamma (`--shape --scale`); with `--reason`/`--source`/`--origin`. `sd uncertainty`, `sd clear-uncertainty`.
- **`sd roles` / `sd equations` / `sd stocks` / `sd constants` / `sd tables`** — listings (`sd roles` gives each variable's name in equations).

## Base-case analysis

- **`sd simulate`** — a deterministic run (`--final-time`, `--dt`, `--saveper`, `--method euler|rk2|rk4|adaptive`, `--time-units`). `--scenario NAME` (repeatable) and `--set "Variable=value [units]"` add what-ifs, each compared with the baseline (end, peak, change). The result is recorded and shows in reports; `--json` prints the full series.
- **`--apply-to-all "Variable=value"`** on `sd simulate`, `sd monte-carlo`, `sd compare` and `sd sensitivity` — values that hold in every run, the baseline included (a high-load world, say). `--set` instead adds an unsaved what-if as one more scenario.
- **`sd loops`** — which feedback loop drives the behaviour, and when (Loops That Matter, with the 2023 flow-to-stock revision): loops through the stocks and equations are scored at each step, and a loop (or the fewest loops) holding half the score dominates. Dominant loops built on unsourced or contested links are flagged. Scores are zero when the stocks stop changing — the method explains change, not equilibrium.

## Option comparison

- **`sd compare <variable> -s OptionA -s OptionB`** — options under uncertainty: the baseline (the model with no scenario changes) and each saved scenario run on the *same* sampled draws, so each difference is measured draw by draw. Gives each option's median, 95% range and central-value run, the paired difference from its **reference** and the share of draws where it is lower or higher (`--metric`, including `total`, the sum over the run). The reference is named on every row: an option that extends a compared scenario is measured against it (delayed vs undelayed — the cost of waiting), the rest against the baseline; `--reference NAME` sets one reference for every option. A delayed-sounding option measured only against the baseline, or one whose parent isn't compared, gets a warning. Each claim names the result, the metric, the reference and the world it holds in. Shown as an options table in the report.

## Uncertainty analysis (Monte Carlo)

- **`sd monte-carlo`** — samples every value that has a range (Latin hypercube by default, `--seed` for repeatability, `--runs` up to 1000) and reports each variable's percentile bands over time (50/75/95/100% of runs) and which uncertain values drive the spread (rank correlation).

## Sensitivity analysis

- **`analyse global-sensitivity sd --variable <variable> [--metric …] [--method sobol|morris]`** — every ranged value varied at once: each one's share of the result's variance, alone and through interactions (see the Analyse Canvas topic). Needs two or more ranges.
- **`sd sensitivity <variable>`** — a tornado: each constant and initial value swung across its range's 5th–95th percentile (or ±10%), ranked by how far it moves one result (`--metric final|peak|peak-time|min|mean|total|at:T`); values with a stated range rank apart from ±10% probes, values with no effect in the run are marked inactive, and values that aren't human-verified are flagged.

## In the editor

In **Formalise**, double-click the canvas for a new factor (name and role, placed where you clicked) and drag from one factor to another to link them — a flow when it joins a flow to a stock or cloud, otherwise an information link — or use **Add to the model**, and select a factor to give it a role and its equation, value or graphical function; the canvas draws it as the report does (stock box, flow valve with its equation, constant with its value, source/sink cloud), and the readiness panel lists what's missing. In **Analyse**, the pane with nothing selected runs the simulation (clock overrides and saved scenarios to compare), saves scenarios (a scenario can build on another: its values, then the new ones), and runs Monte Carlo, sensitivity and loop dominance; **Options compared under uncertainty** (under More analyses) compares scenarios on the same draws, with values that hold in every run; selecting a constant or stock sets its uncertainty, and selecting any factor shows it over the last run. Every run is recorded and appears under **Recorded results** with the report's charts. **Model clock** (Formalise, nothing selected) stores the time unit, start, end, step and method with the model (`sd set-settings`); a selected factor's **Take out of the simulation** drops its role and values, keeping it in the map (`sd unset-role`).

## Results in reports

Simulations, Monte Carlo runs, sensitivity and loop analyses (and BN queries) are recorded. Reports show the latest run of each analysis in a **Results** section — with charts in the hosted report and Word — and the interpretation's claims include what they found. Each heading says what the run was of (its scenarios, evidence or interventions) and when it ran. A result computed before the model last changed is marked out of date — and only a change to what that model type is made of counts, so editing the loop map doesn't age a simulation sharing its map. `latris results list` shows what reports use; `latris results hide <run>` leaves one out. A `latris link` carries the parameters and the analyses, and opening it recomputes the same results. An analysis that read a dataset (effect or impact estimation) can't be re-run without the data, which links don't carry, so its result travels as the sender's, and the report says it was computed by the sender and from which dataset.

## Integration methods

Once a model passes its unit check it runs on a compiled float path (identical results, many times faster), which is what makes hundreds of Monte Carlo runs practical; models with offset units such as degC use the slower unit-checked path. `euler` is fixed-step forward Euler at `dt`. `rk4` and `rk2` use scipy's adaptive Runge–Kutta (RK45 / RK23) bounded to never step past `dt` — close to, but not bit-identical with, the classical fixed-step RK4 of Vensim/Stella. `adaptive` lets scipy choose its own steps. Halving `dt`, or comparing `euler` with `rk4`, is a quick check that results aren't integration artefacts.

## Not yet

Calibration to data, arrays (subscripts), table or mid-run changes in scenarios, correlated uncertainty, strongest-path loop search for very large models (over 500 loops), AI-drafted equations, XMILE/Vensim import/export (which would strip provenance) are out of scope for now. A simulation is a scenario conditional on its assumed structure and parameters, not a forecast.
