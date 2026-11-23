# Contract and predict — design

*Status: first cut built (roadmap #17). The code is the truth for details: `schema/contract.py`,
`operations/contract.py`, `operations/predict.py`, `operations/predictors/`, `api.py`.*

## What it is for

A model that has been built and argued for in Latris should be usable somewhere else: a script, a
notebook, a scheduled job. That needs two things the workbench didn't have.

- **A contract.** The model says which of its values a caller may set (inputs) and which results it
  returns (outputs), under stable names.
- **A stateless run.** A caller gives values, gets outputs back, and nothing is written to the project.

Because a project is a git repository, a caller can **pin a version**: run the model exactly as it was
at a commit a person signed off, and know from the result which commit that was.

This is not a way to run black-box predictors. Every number a prediction returns still comes from
formulas, tables and parameters a person can source, check and challenge.

It is also not the *predictions* register (`latris prediction add`): that records a forecast a person
makes so it can be checked later. Predict runs the model.

## The contract

One file per model type, committed with the model: `views/contracts/<model_type>.yaml`.

| | Fields |
|---|---|
| Input | `name`, the factor it sets, `kind` (`value`: a number with `units`; `state`: one of a factor's states, observed or `set` as an intervention), optional `default`, valid range, `required`, description |
| Output | `name`, the factor, `kind` (`value`, `series`, `distribution`), `units`, `metric` (which value of a run: final, peak…), description |

**Names are the interface.** A caller writes `flow_depth`, not a factor id or a label, and the name
stays when the factor is renamed.

**Declaring is deliberate.** `contract init` drafts a contract from the model (what it treats as given
goes in, what it is for comes out); a person then prunes it. An input is a promise to every caller, so
nothing is exposed by default beyond the draft.

**An input left out** takes the contract's default, else the model's own value. **A value outside its
valid range** is used as given and reported as a warning: an extrapolation is shown as one, never
clamped. The range is the contract's own where it states one, else the model's.

**An output's units are a promise too.** They are set when the output is declared and kept after that:
the model computes in its own units and `predict` converts the result to the contract's (a value, or
every value of a series). If the model's units stop being convertible (metres became seconds),
`contract check` says so and `predict` refuses; declaring the output again takes the model's units. A
measure of a run has the units of the measure: `peak-time` is in the clock's units, `total` in the
variable's units times time (a flow in tonne/year totals to tonne). `at:T` must lie inside the time the
model runs over; `contract output` and `contract check` both refuse one that doesn't.

**A name stands for one factor.** `contract output --name` changes the output of that name; it refuses
a name that already stands for a different factor (remove it first), so a caller is never silently
handed something else.

The contract lives outside `views/parameters/` on purpose: editing it must not make recorded analysis
results look out of date. If a factor it names is deleted, the contract is not silently trimmed:
`contract check` reports the dangling entry.

## What each model type offers

`Formalism.predictor` names a module in `operations/predictors/` with `build(paths) -> Predictor`: the
model loaded and compiled once, listing what could be an input or an output, with a pure
`run(values, modes, outputs)`.

| Model type | Inputs | Outputs |
|---|---|---|
| Equation model | inputs and parameters (value, units) | any formula's value |
| System dynamics | constants and stocks' starting values | a variable's whole run (`series`) or a measure of it (`value` with a `metric`) |
| Bayesian network | a factor's state, observed or set | the probability of each state (`distribution`) |

Not yet: fault trees, bow-ties, event trees, decision trees and Markov models (their Monte Carlo code
already has an inputs-to-outputs function to build on); MCDA and FCM. Never: theory of change, ACH and
argument maps, which have no forward calculation.

## Predict

`predict.load(model_type=, ref=, root=)` returns a `LoadedModel`; `LoadedModel.predict(inputs)` returns

```
outputs     {name: {value | series | distribution, units, label}}
inputs      {name: {value, units, source: given | default | model}}
warnings    [an input outside its valid range, unsaved changes, the model's own notes]
provenance  {project, model_type, ref, commit, uncommitted_changes, contract_hash,
             latris_version, review: {version, maturity, milestone}}
```

A given value is a number in the input's units, a string with units (`"250 cm"`), or
`{"value": 250, "units": "cm"}`; compatible units are converted, incompatible ones refused. An empty
`ref` means the working folder, as no `ref` does.

`model_type` is checked against the model types latris knows before anything is read, and the path
helper (`layout.contract_path`) refuses anything that isn't a plain identifier: a caller's text never
chooses a file.

`predict` never refuses a version for being unreviewed: it reports the review state and leaves the
decision to the caller. A pipeline that wants a gate passes `require="approved"` (or `"reviewed"`).

## Pinning a version

`ref` is a milestone's name, anything git can name (a commit, a prefix, a branch), or a version's name.
Everything in Latris reads a project from a folder, so a pinned run exports that commit once into a
cache folder (`~/.cache/latris/pinned/<commit>`, or `LATRIS_CACHE_DIR`) and loads from there
(`git.export_commit`: a local clone with no checkout, then a detached checkout; the source repository
is not touched). A commit never changes, so the cache is never stale.

A version written by a much older or newer latris may not load; the error says so. Projects don't
record the latris version that wrote them, so a pipeline should pin its latris version as well as the
model's commit.

## What changed between two versions

`contract.compare(base, head)` sorts the difference by what it means for a caller:

- **breaking**: an input or output removed or renamed, pointed at a different factor, its kind or units
  changed, an input made required, a new required input; also an output whose contract is unchanged
  but whose model no longer gives units the contract's can be converted from (found by loading the
  model at both versions);
- **compatible**: an optional input or an output added, a default or valid range changed;
- **internal**: the same contract, but the model behind it changed (anything under `substrate/`,
  `views/roles/`, `views/parameters/`), so the same inputs may give different outputs;
- **same**.

`latris contract diff` exits 1 on a breaking change, so a pipeline can refuse to upgrade.

The contract's hash covers the same things: names, the factors they stand for, kinds, units, modes,
metrics and whether an input is required. (The factor was added after 0.17.0, so a hash
recorded by an earlier latris differs from the one computed now for the same contract.)

## Surfaces

- **Python:** `latris.load(path, ref=...)` returns a `latris.Model` with `.contract`, `.predict(inputs)`
  and `.predict_many(rows)`. This is the library's first public API; everything under
  `latris.operations` and `latris.schema` stays internal.
- **CLI:** `latris contract init | show | available | input | output | remove | check | diff` and
  `latris predict`.
- **Server:** `/api/contract*` and `POST /api/predict`.

## Not in the first cut

- **Time-series inputs** (forcing, roadmap #19). A caller who needs a series today loops over single
  values in their own code.
- **Uncertainty bands** on a prediction, from the model's stated ranges.
- **A hosted endpoint.** Pipelines clone the project and call the library. A hosted one needs API keys
  and read-only project access, neither of which exists.
- **Git tags for milestones.** A milestone is still a record in the project; `--ref` finds it by name.
- **The model types listed above as "not yet".**
