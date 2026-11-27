---
title: Theory of Change
category: model-types
summary: Lay out how an intervention is meant to reach its impact, and see which steps the evidence holds up.
place: frame.model_type
---

## What a theory of change represents

A theory of change is a results chain: what an intervention does (**activities**), what that directly produces (**outputs**), the changes that follow (**short-term** and **long-term outcomes**), and the long-term change it is for (**impact**). **Inputs** are the resources it uses. Every factor gets one of these levels (`latris toc level <factor> <level>`); links are ordinary causal links that run forward through the levels. The impact is the outcome of interest.

## Structural analysis (pathways and their evidence)

`latris toc check` lays out every pathway from an activity to an impact and, for each link on one, what holds it up:

- **checked** — a source was read and found to support it;
- **cited** — it has a source nobody has checked yet;
- **untested** — no source at all;
- **contested** — a source argues against it.

A pathway is only as strong as its weakest link. The check also counts the assumptions stated for each link (`latris assumption add ... --target "A -> B"`) and flags *leaps*: links that skip two or more levels (an output straight to the impact), where the steps between are left unstated. The result is recorded, so the report's Results section shows it, and it goes out of date when sources, checks or assumptions change.

## Base-case analysis (process tracing)

_How far does the evidence support each link?_

The check says whether a link has evidence; process tracing says how much that evidence should move you. For each link, set how confident you are before looking (`latris toc prior "A -> B" 0.6`; 0.5 if unset), then add **tests** — evidence you'd expect to see if the link holds — with two judgements: how likely you'd find it if the link holds (`--if-true`, its certainty) and if it doesn't (`--if-false`; low means the evidence is unique to the link):

    latris toc test "Mentoring -> Engagement" "attendance rises" --if-true 0.9 --if-false 0.4

Once you've looked, record the result (`--found` or `--not-found`). The test's type follows from the two numbers (Van Evera's four):

- **hoop** (certain, not unique): failing it sinks the link; passing it helps only a little;
- **smoking gun** (unique, not certain): passing it strongly supports the link; failing it hurts little;
- **doubly decisive** (both): settles it either way;
- **straw in the wind** (neither): nudges only.

`latris toc trace` updates each link from its prior through the tests carried out (Bayes' rule in odds form), gives each pathway a confidence (the product of its links, treating them as independent) and its weakest link, and ranks the tests still to run by how far they could move their link. It is recorded, so the report shows it and the interpretation's claims include it. The numbers are judgements: write down why in `--notes`, cite where the evidence was found with `--source`, and mark them `--verified` once someone has reviewed them.

## Estimation from data (impact)

_Did the outcome change when the intervention started?_

With data on an outcome over time (`latris data add`), `latris toc impact` estimates the change:

- **Interrupted time series** (no comparison group): `latris toc impact Attendance --dataset monthly --time month --at 2024-01-01`. It fits the trend before the start, the step at the start and the change of slope after it, and compares the last period with the pre-period trend projected forward. At least 8 periods on each side are advised; the errors are modelled as autocorrelated (AR(1)), so month-to-month persistence doesn't make the interval falsely narrow.
- **Difference-in-differences** (a comparison group): add `--group <column> --treated <value>` (repeat `--treated` for several). It compares the treated group's change with the comparison group's, after checking whether their trends were already diverging before the start. With 20 or more groups the errors are clustered by group; with fewer, it says the interval is likely too narrow.

Each check that fails or can't be made is listed as a caution with the result, and the result states what it assumes: for a time series, that nothing else changed at the same time; for difference-in-differences, that the groups would otherwise have moved in parallel. These are the designs' weak points and the data can only partly test them. The estimate is recorded and goes out of date when the dataset changes.

## Readiness

The model is ready when every factor has a level, no link runs backwards (towards activities), there is at least one activity and one impact, every impact is reached from an activity, and nothing dead-ends before the impact.

## Practical caution

The check is structural and about evidence. It shows where a theory rests on untested or contested steps — where to look first in an evaluation — not how big an effect is; for that, use the impact estimate, within its assumptions. Methods behind it: Weiss (1995) on theory-based evaluation, the W.K. Kellogg Foundation (2004) logic model, and Mayne (2012) on contribution analysis. Process tracing doesn't estimate effect sizes: it weighs evidence for each causal step, and its answer is only as good as the probabilities given. Methods: Van Evera (1997), Bennett (2015), Befani & Mayne (2014), Fairfield & Charman (2017); for impact, Wagner et al. (2002), Bernal et al. (2017) and Angrist & Pischke (2009).
