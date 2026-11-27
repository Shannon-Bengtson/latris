---
title: Equation Models
category: model-types
summary: Compute with sourced formulas: what a physical law or published relationship gives for your inputs.
place: frame.model_type
---

## What an equation model represents

Quantities joined by formulas, with units and no clock: a physical law, an engineering relationship, a published parameterisation. Each quantity is a factor with one of four roles:

- an **input** is something the model is given (a depth, a dose, a rainfall total): `latris eq input Depth 1.2 m --min 0.2 --max 3`;
- a **parameter** is a coefficient of the method (a roughness, an emission factor): `latris eq parameter Roughness 0.035 "s/m**(1/3)" --source chow-1959 --min 0.025 --max 0.05`;
- a **computed** quantity has a formula over the others: `latris eq formula Velocity "hydraulic_radius ** (2/3) * SQRT(slope) / roughness" m/s --source manning-1891`;
- an **output** is a computed quantity that is a result: add `--output`.

A formula names other quantities by their label in lower case with underscores (Hydraulic radius is `hydraulic_radius`), so work from the inputs up. It can use arithmetic, `**` and `MIN`, `MAX`, `ABS`, `IF_THEN_ELSE`, `EXP`, `LN`, `LOG10`, `SQRT`, `SIN`, `COS`, `TAN` and `MODULO`. Setting a formula adds the links it needs to the map, so the diagram shows what each quantity is computed from.

**Units are checked.** Every value carries its units through the formulas, so a formula that adds metres to seconds, or gives m/s where you declared m, is refused by `latris eq check`. The check also names a factor that is linked into the model but has no role, and a scenario or uncertainty range that no longer fits its value. Changing a value's units converts its uncertainty range with it; a change to units of a different kind is refused until the scenarios and range that depend on it are removed. Where an empirical formula hides units in a coefficient, give the coefficient those units (Manning's roughness is in `s/m**(1/3)`).

**Valid ranges.** `--min` and `--max` state the range a value is good for, usually the range its source covered. Every analysis reports a value outside its range as an extrapolation. Nothing is clamped: you see the number and the warning together.

## What the analyses show

- `latris eq evaluate` works the model out: every quantity at the reference values, and under each **scenario** you have saved (`latris eq scenario "Design flood" --set "Depth=2.5 m"`).
- `latris eq sweep --input Depth` moves one input across a range (by default its valid range), holding the rest, and gives the output's curve, whether it rises or falls throughout, and how many percent the output changes for a one percent change in the input.
- `latris eq monte-carlo` answers "how sure is the result?": give inputs and parameters a range (`latris eq uncertainty Roughness triangular --min 0.025 --mode 0.035 --max 0.05 --reason "range across the cited channels"`), and it samples them, recomputes, and reports each output's spread and which values drive it.

Each result is recorded for the report with a chart, and goes out of date when a value, formula or range changes.

## In the app

The model is drawn on the Formalise canvas: inputs and parameters as rounded boxes, formulas as square ones (an output in bold), each with its value, and an arrow for each quantity a formula reads. Double-click the canvas to add a quantity, or add the factors in Build: they don't need linking there, because saving a formula adds the links to what it reads. Select a quantity to set its role, value or formula, units, valid range and uncertainty in the inspector. In Analyse, **Evaluate the model** works it out under the reference values and your scenarios (kept in the same pane), and the input sweep and Monte Carlo are under **More analyses**.

## Practical caution

Passing the units check does not make a formula right, and an empirical relationship is only as good as the study behind it: record the source of every formula and coefficient, and state its valid range. Formulas must be explicit; a set that depends on itself is refused, not solved. Temperatures in formulas must be in kelvin. Sweeps move one input at a time, and the Monte Carlo samples ranges independently. Methods: Buckingham (1914) and Bridgman (1922) on dimensional analysis; JCGM 101:2008 on propagating distributions by Monte Carlo.
