# Equation model — design

*Status: built (roadmap #18). The code is the truth for details: `schema/equation_model.py`,
`operations/equation_model.py`, `operations/formalisms/equation_model.py`.*

## What it is for

A model made of **sourced formulas**: a physical law, an engineering relationship, a published
parameterisation. Inputs go in, formulas turn them into outputs, and there is no clock. Manning's
equation for channel flow, a Penman-style evaporation estimate, an emission-factor calculation and a
dose-response curve are all this shape.

It earns a model type of its own because system dynamics, the nearest type, is built around stocks
that accumulate over time: an algebraic model would need an invented stock and an invented time axis.
What the two share is the equation engine, and the equation model reuses it.

It is the most defensible kind of model Latris holds, because every formula and every coefficient
can name the paper it came from and the range it was fitted over. That is the "inspectable only"
principle of the roadmap, not an exception to it.

## Shape

Quantities are ordinary substrate factors with a view role (`views/roles/equation_model-roles.yaml`):

| Role | Is | Carries |
|---|---|---|
| `input` | something the model is given: rainfall, slope, dose | a reference value, units, an optional valid range |
| `parameter` | a coefficient of the method: a roughness, an emission factor | a value, units, an optional valid range |
| `computed` | an intermediate quantity | a formula and its units |
| `output` | a computed quantity that is a result | a formula and its units |

Stored, one entry per quantity, each with its own provenance (`EntryBase`):

- `views/parameters/equation_model-value.yaml` — `EquationValueSet` (inputs and parameters);
- `views/parameters/equation_model-formula.yaml` — `EquationFormulaSet` (computed quantities and outputs);
- `views/parameters/equation_model-scenarios.yaml` — `EquationScenarioSet` (named sets of input values);
- ranges for Monte Carlo live with every other type's, in `parameter-uncertainty.yaml`
  (cell `equation_model:value`).

An input and a parameter are stored the same way. The role says which is which: an input is what a
caller supplies (a scenario, a sweep, later a pipeline), a parameter belongs to the method.

### Formulas

A formula references other quantities by their slugified labels (`Hydraulic radius` →
`hydraulic_radius`), exactly as SD equations do. It is parsed and evaluated by the same sandbox
(`operations/_sd_eval.py`), with values bound to `pint` quantities, so a unit error is an evaluation
error. The equation model allows the functions that mean something without a clock (`ALGEBRAIC_FUNCTIONS`:
`MIN`, `MAX`, `ABS`, `IF_THEN_ELSE`, `EXP`, `LN`, `LOG10`, `SQRT`, `SIN`, `COS`, `TAN`, `MODULO`) and
refuses `TIME` and the time functions (`STEP`, `RAMP`, `PULSE`, the delays). SD's own function list is
unchanged.

An empirical formula whose coefficient hides units (Manning's *n*) is handled the honest way: the
coefficient is a parameter with those units (`s/m**(1/3)`), so the dimensional check still passes.

### Links

A formula's references are the model's structure, and the map shows them as ordinary causal links, so
the diagram, the canvas and evidence on links all work as they do everywhere else. Setting a formula
adds any link it needs in the same commit. The structure check reports a link the formulas don't use
(`eq_unused_link`) and a reference with no link (`eq_missing_link`, e.g. after a link was deleted).

### The valid range

An input or parameter may state the range its value is good for (`valid_min`, `valid_max`), usually the
range the cited study covered. Every run reports values outside it. Nothing is clamped: an
extrapolation is shown as one, beside the number.

## Analyses

| Result kind | Analysis | Answers |
|---|---|---|
| `eq-evaluation` | `eq_evaluate` | The value of every quantity at the reference inputs and under each scenario. |
| `eq-sweep` | `eq_sweep` | How an output responds as one input moves across a range, the others held. |
| `eq-monte-carlo` | `eq_monte_carlo` | The spread of the outputs given the ranges on inputs and parameters, and what drives it. |

## Structure problems

`eq_no_output`, `eq_unclassified` (a factor linked into the model with no role), `eq_no_value`,
`eq_no_formula`, `eq_formula_invalid`, `eq_unknown_reference`, `eq_name_collision`, `eq_circular`,
`eq_units`, `eq_missing_link`, `eq_unused_link`.

A circular set of formulas is refused, not solved: simultaneous equations are out of scope.

## Built for predict (#17)

`equation_model.compute(model, values)` is a pure function: values in, every quantity out, nothing
read from or written to the project. The inputs with their units and valid ranges, and the outputs,
are already the input/output contract predict needs to declare. Predict wraps this; the equation
model does not need to change for it.

## Not in the first version

- Lookup tables (`TABLE`) and time-series inputs.
- Simultaneous (circular) equations and root finding.
- Global sensitivity (Sobol, Morris): the layer exists for other types; adding this one is a small
  follow-up.
- Units with an offset (°C, °F) in arithmetic: use kelvin, as `pint` requires.
