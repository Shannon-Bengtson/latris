# Predict for the remaining model types — plan

*Status: agreed, not started (roadmap #17 follow-up). Extends [PREDICT.md](PREDICT.md), which covers what is
built: the contract, the stateless run and pinned loading, with predictors for the equation model,
system dynamics and Bayesian networks.*

The goal is a predictor (`operations/predictors/<type>.py`, named by `Formalism.predictor`) for every
model type with a forward calculation:

| Order | Model type | Kernel it wraps |
|---|---|---|
| 1 | Fault tree | `_ft_engine.build_bdd` + `BDD.probability` (as `risk_uncertainty._ft_model`) |
| 2 | Bow-tie | `bow_tie._frequencies` (as `risk_uncertainty._bt_model`) |
| 3 | Event tree | the sequence products in `risk_uncertainty._et_model` |
| 4 | Decision tree | `decision_tree.rollback`, with `psa._dt_inputs.apply` to set values |
| 5 | Markov | `markov.totals` / `run_strategy`, with `psa._mk_inputs.apply` to set values |
| 6 | MCDA | `mcda.values` + the weighted sum in `mcda.analyse` |
| 7 | FCM | `fcm_inference.fcm_infer` with `clamped` |

Theory of change, ACH, argument maps, CLDs and DAGs stay without a predictor because they have no
forward calculation.

The order goes from least to most new contract machinery. The three risk types need only one
addition to the contract (step 0a). Decision trees and Markov models need it in full, plus a new
output kind. MCDA and FCM are last because what their numbers mean needs a caveat on the contract
(see their sections).

## Step 0 — shared groundwork (before any new predictor)

### 0a. Address a parameter, not just a factor

A contract entry today is keyed by `target_id` alone, and `Contract._unique` allows one input per
factor. That is too coarse for the new types:

- **Markov:** the same edge has a transition probability per strategy, and the same state has a cost
  and a utility per strategy.
- **Event tree:** a heading has one probability per branch prefix (`given`).
- **Decision tree:** a branch has both a probability and a value.
- **MCDA:** a score belongs to an (option, criterion) pair.
- **Markov and decision-tree outputs:** a strategy has a cost, an outcome, an ICER and so on.

**Proposal:** add an optional `cell: str | None` to `Candidate`, `ContractInput` and `ContractOutput`,
using the `parameter_cell_id` vocabulary that PSA and risk Monte Carlo already use
(`markov:transition:<strategy>`, `event_tree:probability:<given>`, `decision_tree:payoff` and so on;
`psa.describe_cell` parses them). Identity then becomes `(target_id, cell)`:

- `_unique` checks inputs by `(target_id, cell)`;
- `contract_hash` includes `cell` (when it is absent, the hash of an existing contract is unchanged);
- `contract.compare` treats a changed cell as breaking;
- the predict loop, `contract available` and `contract input|output` all key by the pair;
- the CLI takes `--cell`, or a qualifier flag per type (`--strategy`, `--given`) that builds it.

The payoff of reusing this vocabulary is that a contract input and an uncertainty range on the same
parameter share an address. That is exactly what *uncertainty bands on a prediction* (the other open
#17 follow-up) needs, so that follow-up becomes a join rather than a mapping.

The schema change lands first, with round-trip tests (*schema before code-that-uses-schema*).

### 0b. A `choice` output kind

A decision tree's best option and an MCDA's top-ranked option are labels, not numbers or
distributions. Add `OutputKind = "choice"`: the value is one of `Candidate.states` (the options), it
has no units and no metric, and `predict` returns `{"choice": "<label>"}`.

Rankings are left out. A caller who wants one asks for each option's value.

### 0c. One kernel per type, shared with Monte Carlo and PSA

The functions from inputs to outputs that the risk Monte Carlo (`risk_uncertainty._ft_model`,
`_bt_model`, `_et_model`) and PSA (`psa._dt_inputs`, `_mk_inputs`) build today are the predict kernels.
Move each into its predictor module. `risk_uncertainty` and `psa` then build their `_Model` / `apply`
from the predictor, so the deterministic run and the sampled runs cannot drift apart.

Each move is its own commit, and the existing Monte Carlo and PSA tests must pass unchanged.

### 0d. Units that aren't physical

Decision-tree payoffs, Markov costs and MCDA values are in a currency, QALYs, or no unit at all. The
contract requires units and converts them through `_units` (pint), which has no currencies. **Decided:**

- **(chosen)** Treat a unit pint can't parse as an *opaque* unit. The contract records it
  verbatim, conversion is identity only, and a mismatch is refused. `GBP → USD` is never converted
  silently.
- ~~Register currency codes as base dimensions in the unit registry.~~ Not chosen.

Probabilities and activations are `dimensionless`, with a model valid range of 0–1 (FCM: the
activation function's range).

### 0e. A shared invariant test

For every predictor, `run({}, {}, all_outputs)` must equal the point estimate from that type's own
`analyse()`. This is one parametrised test in `tests/operations/test_predict.py`, which every new
predictor joins.

## Per model type

Each section below lists the inputs (`Candidate`, with `suggested` marking what `contract init`
drafts), the outputs, the validation `run` does, and what is deliberately left out.

### 1. Fault tree

- **Inputs:** each basic event's probability. `cell` is `fault_tree:probability`, units
  `dimensionless`, model range 0–1, all suggested.
- **Outputs:** the top event's probability (suggested), and any intermediate gate's probability
  (build a BDD per requested gate, cached on the predictor).
- **Run:** `bdd.probability(root, p)`. A probability outside 0–1 is refused, not warned: the
  probability is impossible, not an extrapolation.
- **Problems:** what `structure_problems` returns, plus any basic event that has no probability.
- **Not now:** importance measures as outputs (Birnbaum, Fussell–Vesely). They are a natural later
  `value` output on a basic event.

### 2. Bow-tie

- **Inputs:**
  - threat frequencies: `bow_tie:frequency`, units from the model (per year), suggested;
  - barrier PFDs: `bow_tie:pfd`, dimensionless, 0–1;
  - each barrier's status as a **state** input (`in_place` / `not_in_place`), so a caller can ask
    "what if this barrier is down?" without knowing its PFD. `not_in_place` forces PFD = 1, as
    `_bt_model` already does.
- **Outputs:** the top event's frequency (suggested) and each consequence's frequency.
- **Run:** `_frequencies(bt, pfd, freq)`, with the status override applied first.
- **Not now:** a barrier's "effectiveness" flag as an input. It stays a model judgement.

### 3. Event tree

- **Inputs:**
  - the initiating-event frequency (`event_tree:frequency`, suggested);
  - each heading probability per branch prefix (`event_tree:probability:<given>`). The label shows
    the condition (`P(Sprinklers = yes | Alarm = no)`), exactly as `_et_model` writes it today.
- **Outputs:** each end state's frequency (or probability, when there is no initiating frequency).
  The suggested output is the rarest bad end state, as Monte Carlo chooses it now.
- **Run:** the sequence products, summed per end state and scaled by the frequency.
- **Watch:** an end state reached by several sequences is a single output, the sum over them, which
  matches `analyse`.

### 4. Decision tree

- **Inputs:**
  - terminal payoffs: `decision_tree:payoff`, in the tree's units, suggested;
  - branch values: `decision_tree:value`;
  - chance probabilities. A two-branch chance node takes one `decision_tree:probability` (the other
    branch is its complement), and a node with more branches takes one per branch.
- **Shared uncertainties:** setting a probability on one chance node sets it on every node that
  shares the uncertainty (the `siblings` logic in `_dt_inputs.apply`). A contract may name only one
  node per uncertainty, and `contract check` says so.
- **Outputs:**
  - each option's expected value at the root (`value`, the tree's units, suggested);
  - the best option (`choice`, suggested);
  - EVPI (`value`), which costs a full rollback per state combination, so it is offered but not
    suggested.
- **Run:** apply the inputs, then `rollback(t)`. A multi-branch node whose given probabilities don't
  sum to 1 within 1e-6 is refused, naming the node. They are not rescaled, because rescaling would
  hide a caller's error.
- **Not now:** `thresholds` (where the decision flips). That is an analysis, not a prediction.

### 5. Markov cohort

- **Inputs** (all with `cell` carrying the strategy where the model has strategy-specific values):
  - transition probabilities: `markov:transition[:<strategy>]`, 0–1;
  - per-cycle costs and utility weights: `markov:cost|utility[:<strategy>]`, suggested;
  - starting proportions per state (a `markov:start` cell, 0–1). They must sum to 1, otherwise the
    run is refused;
  - from settings: the discount rates (dimensionless, 0–1) and the horizon in cycles. The horizon is
    the only input that changes the shape of the trace output.
- **Outputs, per strategy:**
  - discounted cost, suggested;
  - discounted outcome (QALYs or the model's own measure), suggested;
  - undiscounted cost and outcome;
  - time in each state (cell `markov:time_in:<state>`);
  - the state-occupancy trace as a `series` per state (times are cycle × cycle length, and
    `time_units` comes from the settings).
- **Outputs across strategies:**
  - the incremental cost and outcome and the ICER against the comparator (from `incremental`);
  - net monetary benefit at a willingness-to-pay. That needs a WTP, which would be one more input
    (`markov:wtp`) with the settings' value as its default.
- **Run:** apply the inputs, then `run_strategy` for each strategy needed. A row of transitions
  leaving a state that sums to more than 1 is refused. `transition_matrix(rescale=False)` already
  detects this.
- **Watch:** ICER is undefined when the incremental outcome is 0, and the sign matters (dominated or
  dominant). Return `None` plus a warning, not ±inf.

### 6. MCDA

- **Inputs:**
  - each criterion's weight (`mcda:weight`, dimensionless, suggested);
  - each option's score on a criterion (`mcda:score:<option>`, in the criterion's own units). This is
    how a pipeline scores a new measurement against the agreed criteria.
- **Outputs:** each option's overall value (0–1, suggested) and the top option (`choice`,
  suggested).
- **Run:** `values(...)`, then the weighted sum. Weights are normalised to sum to 1, and a warning
  says so if they didn't.
- **Caveat on the contract:** a criterion with no fixed scale is scaled *locally*, from the worst to
  the best option. Changing one option's score can then move every option's value. `contract check`
  warns for each locally scaled criterion with a score input on it, and recommends fixing its scale
  (`mcda criterion --worst/--best`). `run` repeats the `outside:` notes from `values` as warnings.
- **Not now:** adding or removing options per call.

### 7. FCM

- **Inputs:**
  - concepts clamped at an activation (`value`, dimensionless, within the activation function's
    range). A clamp holds a concept at that value: the "scenario" in `fcm-inference`;
  - optionally, a starting activation for a concept left unclamped;
  - all are offered, and the suggested ones are the concepts with no incoming links.
- **Outputs:** each concept's activation at steady state (suggested: the outcome).
- **Run:** `fcm_infer(edges, weights, ids, clamped=..., initial=..., settings=...)`. A run that
  doesn't converge, or that oscillates, returns its last state with a warning.
- **Registration:** FCM has no plugin of its own (it is `_causal("fcm")` in
  `formalisms/causal.py`), so add `predictor=` there.
- **Caveat:** FCM activations are relative and semi-quantitative. The predictor's candidates say so
  in `role`, and the help topic says a caller should compare scenarios, not read absolute levels.

## For every type: the definition of done

Following TESTING.md, each type lands as its own PR with:

1. `operations/predictors/<type>.py` and `predictor=` on its `Formalism`;
2. tests for its candidates, defaults, refusals, warnings and the invariant from step 0e. For risk,
   decision-tree and Markov models, the existing Monte Carlo and PSA tests must pass unchanged after
   the kernel moves;
3. a `contract init` + `predict` block in `worked_example/worked_example.py`, with the transcript
   regenerated (`pytest tests/test_worked_example.py --slow`);
4. the type's row added to the table in PREDICT.md → "What each model type offers", and its entry
   removed from "Not yet";
5. the help topics updated: `use-in-a-pipeline.md`, plus the type's own model-type topic;
6. in latris-app, the Use view (`gui/src/components/use/`) rendering what is new. That is `choice`
   outputs once (step 0b), and the `cell` qualifier in input and output labels once (step 0a). Every
   later type then needs no GUI work beyond a journey test. The MCP `predict` tool is generic and
   needs nothing.

## Rough sizing

| Step | Effort |
|---|---|
| 0a–0e groundwork (schema, hash, compare, CLI qualifier flags, units decision, invariant test) | 1.5–2 days |
| Fault tree, bow-tie, event tree (mostly a move of existing code) | ~1 day together |
| Decision tree | 1 day |
| Markov (most outputs; the ICER edge cases) | 1.5 days |
| MCDA | 0.5 day |
| FCM | 0.5 day |
| App: `choice` + cell labels in the Use view | 0.5–1 day |

That is about a working week and a half for all seven, with each type shippable on its own once
step 0 is in.

## Decisions (agreed 2026-11-25)

1. **`cell` on the contract (0a):** reuse the `parameter_cell_id` vocabulary.
2. **Units (0d):** a unit pint can't parse is opaque: recorded verbatim, identity conversion only, a
   mismatch refused.
3. **`choice` output kind (0b):** added.
4. **FCM:** included, for completeness, with the caveat on its numbers above.
