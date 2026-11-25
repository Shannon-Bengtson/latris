---
title: Fault Trees
category: model-types
summary: Break an undesired event down into the failures that cause it; find cut sets, its probability and what matters most.
---

## What a fault tree represents

A fault tree starts from one undesired **top event** and works down through **gates** to the **basic events** that, in combination, cause it. Each factor gets a type (`latris ft event <factor> top_event|intermediate_event|basic_event|undeveloped_event`); link each input to the event it feeds (`latris edge add <input> <event> --kind logical`, or a causal link). Every top or intermediate event has a gate (`latris ft gate`): **and** (all inputs must occur), **or** (any one is enough) or **vote** with k (at least k of them, e.g. 2-out-of-3 redundant supplies). Undeveloped events are leaves you chose not to break down further.

Only factors with a fault-tree type are in the tree, so a fault tree can share its events with a causal loop diagram. A link into the tree from an unclassified factor is left out and listed, never silently used.

## What the analysis shows

`latris ft analyse` lists the **minimal cut sets** — the smallest combinations of basic events that cause the top event — and the **single points of failure** (cut sets of one event). Give every basic event a probability (`latris ft probability <event> <p> --source <where>`) and it adds:

- the **exact top-event probability**, from a binary decision diagram, so an event that feeds more than one gate isn't double-counted (the rare-event approximation and min-cut upper bound are shown beside it);
- each event's **importance**: Fussell–Vesely (the share of the top-event probability that needs it), Birnbaum (how far the top-event probability moves between the event surely happening and surely not) and RAW (how many times likelier the top event is if it happens).

Every probability keeps where it came from; the important ones nobody has verified are flagged, so you know which numbers to check first. The analysis is recorded for the report and goes out of date when the tree or a probability changes.

## How sure is it? (Monte Carlo)

Basic-event probabilities are rarely known exactly. Give them a range — `latris ft uncertainty "Pump A fails" --median 0.01 --error-factor 3` is a lognormal whose 95th percentile is three times its median, the usual way probabilistic risk assessments state it; `uniform --min --max`, `triangular`, `beta` and others also work — then `latris ft monte-carlo`. It recomputes the exact top-event probability for each sample and gives its 5th–95th percentile, median and mean beside the point estimate (with skewed ranges the mean is higher: the point estimate is not the expected value), and ranks the uncertain events by how strongly they drive the spread. Events without a range stay fixed and are listed. Ranges are judgements too: say why with `--reason` and cite with `--source`.

## Calling it from a script (contract and predict)

Once it is quantified, a fault tree can have a contract (see **Using a Model Elsewhere**). `latris contract init fault_tree` drafts one: each basic event's probability goes in, the top event's probability comes out. Any other gate can be an output too (`latris contract output fault_tree "Power lost"`). `latris predict --set pump_a_fails=0.05` then gives the exact top-event probability for those values. A probability below 0 or above 1 is refused: it is impossible, not an extrapolation.

## Readiness

The tree is complete when it has one top event, every top and intermediate event has a gate and inputs (and a vote gate's k fits), basic and undeveloped events have no inputs, nothing loops, and every event leads to the top event. Probabilities aren't needed to be ready — the cut sets are useful on their own.

## Practical caution

The analysis is static and assumes basic events are independent: it has no common-cause failure model, no NOT, priority-AND or sequence gates, and different events' uncertainties are sampled as independent. Methods: the NRC *Fault Tree Handbook* (Vesely et al. 1981), IEC 61025, Rauzy (1993) for the decision diagram, and Birnbaum (1969) and Fussell (1975) for importance.
