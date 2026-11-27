---
title: Choosing a Model Type
category: model-types
summary: How to choose between the fifteen model types — systems, causal inference, evaluation, risk, decisions, arguments and equations — by the question each one answers.
place: frame.model_type
---

## Current stable model types

- **CLD:** best for feedback systems and reinforcing or balancing loops.
- **DAG:** best for causal direction, dependencies, and acyclic reasoning.
- **FCM:** best for semi-quantitative influence modelling with weights.
- **BN:** best for quantitative probabilistic reasoning over an acyclic causal subgraph (discrete state spaces + CPTs with per-cell provenance). See the dedicated Bayesian Networks topic.
- **SD:** best for how a system with accumulation, delay, and feedback behaves over time — stocks, flows, unit-checked equations, and deterministic simulation. See the dedicated System Dynamics topic.
- **Theory of Change:** best for programme and policy logic — how an intervention's activities are expected to lead, step by step, to its impact, and what evidence and assumptions hold each step up. See the dedicated Theory of Change topic.
- **Fault Tree:** best for how an undesired event can happen — the combinations of failures that cause it, single points of failure, its probability and which failures matter most. See the dedicated Fault Trees topic.
- **Bow-Tie:** best for showing, for one top event, what could cause it, what could follow, and the barriers in between — where the protection is thin, shared or uncontrolled, and (with frequencies and failure probabilities) how often each outcome is expected. See the dedicated Bow-Ties topic.
- **Event Tree:** best for following one initiating event forward — which safety functions work or fail, in what order, and how often each end state results. See the dedicated Event Trees topic.
- **MCDA:** best for a choice between options judged on several criteria — the ranking, what drives it, and how far the weights would have to move to change it. See the dedicated Multi-Criteria Decision Analysis topic.
- **ACH:** best for choosing between competing explanations — which one the evidence fails to rule out, and which pieces of evidence the conclusion turns on. See the dedicated Analysis of Competing Hypotheses topic.
- **Decision tree:** best for a choice whose outcome depends on chance — the best strategy by expected value, what knowing each uncertainty first would be worth, and the probabilities at which the choice flips. See the dedicated Decision Trees topic.
- **Markov model:** best for what happens to a group over time — moving between states such as well, ill and dead — and what each strategy costs and achieves, with cost-effectiveness (ICERs, net benefit). See the dedicated Markov Cohort Models topic.
- **Argument map:** best for a case argued to a board, client or reviewer — whether the conclusion stands, the reasons it stands on, the objections still unanswered and the premises it turns on. See the dedicated Argument Maps topic.
- **Equation model:** best for a model built on physics or published relationships — what the formulas give for your inputs, with units checked, every coefficient sourced, and values outside their valid range flagged. See the dedicated Equation Models topic.

## Which factors are in which model type

A model can be several types at once. Every factor and link is in every chosen type unless you leave it out: select a factor or link on the Build canvas and untick a type under **In these model types** (with a reason, if it helps the reader). It stays out — opening the type doesn't put it back — and a factor's links leave with it. Tick it again to put it back. Each type's report covers what's in it. From the command line: `latris mapping leave-out <factor> <type> --reason "..."` and `latris mapping add <factor> <type>`.

## Planned model types

On the roadmap: influence diagrams (for decisions), and Goal Structuring Notation (for safety cases) as a vocabulary over argument maps. Causal identification is being folded into the DAG view rather than offered as a separate model type.

Other registered types — regression (effect estimation ships as an analysis on DAGs instead: `latris analyse estimate`), fishbone diagrams, flowcharts, state machines and Petri nets — are not currently planned. Any type is admitted only if its reasoning stays inspectable; Monte Carlo / PSA is an analysis layer over parameterized models, not a model type of its own.

## How selection affects the app

Selected model types drive readiness checks, Configure suggestions, Analyse views, and report content. Choose the model types that match the question, not every possible view.

## By the question they answer

- "How does this work — what feeds back on what?" → **CLD**. The cheapest
  honest answer; start here unless the question says otherwise.
- "Can this effect actually be estimated, and from what data?" → **DAG**.
  Adjustment sets and d-separation; with a dataset, the effect size under
  the DAG's stated assumptions (`latris analyse estimate`).
- "How likely is each outcome, and what would change my mind?" → **BN** —
  discrete states and probabilities.
- "Which forces dominate, roughly?" → **FCM** — semi-quantitative weights
  and steady-state tendencies.
- "How will it behave over time if we intervene?" → **SD** — the most
  commitment; build the CLD first.
- "How is this programme supposed to work, and which steps are we taking
  on trust?" → **Theory of Change** — a results chain from activities to
  impact, link by link against the evidence.
- "What combinations of failures cause this, and how likely is it?" →
  **Fault Tree** — gates down to basic events; cut sets, probability and
  importance.
- "What stands between this hazard and harm, and where is it thin?" →
  **Bow-Tie** — threats, barriers and consequences around one top event.
- "Once this happens, how does it play out, and how often does it end
  badly?" → **Event Tree** — yes/no headings from one initiating event to
  end states.
- "Which option should we choose, given what we care about?" → **MCDA** —
  options scored against weighted criteria, and how firm the choice is.
- "Which explanation does the evidence fail to rule out?" → **ACH** —
  competing hypotheses rated against every piece of evidence.
- "What should we do, given what we don't know — and is it worth finding
  out more first?" → **Decision tree** — expected values and the value of
  information.
- "What does each option cost and achieve over years, and is the better one
  worth its price?" → **Markov model** — a cohort moving between states,
  with cost-effectiveness.
- "Does the case hold up, and what does it rest on?" → **Argument map** —
  a conclusion, the reasons for it and the objections to them.
- "What do the equations give for these inputs, and how far can I trust
  it?" → **Equation model** — sourced formulas with units, scenarios,
  sweeps and Monte Carlo.

One substrate carries across: factors, links, evidence and challenges all
stay when you quantify a CLD as FCM/BN/SD later — nothing is redrawn, and
`latris project select-models` records the choice with its rationale.
Triangulating (a CLD plus a DAG on the same substrate) is a strength, not a
mistake. The fuller guide: https://latris.app/formalisms/ — and the methods
behind each formalism, with limits, in docs/FOUNDATIONS.md.
