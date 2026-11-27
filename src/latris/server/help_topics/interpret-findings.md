---
title: Interpret Phase
category: interpret
summary: Turn analysis results into structured findings, claims, and report-ready prose.
place: interpret.findings
---

## What Interpret does

Interpret converts model structure, analysis results, evidence, provenance, and your recorded observations into narrative sections. These sections answer the project foundation and prepare material for reports. Observations you record in the Analyse phase feed the matching section's claims by category.

## Typical sections

- Structural summary.
- Key findings.
- Sensitivity and robustness.
- Assumptions and limitations.
- Evidence gaps.
- Evidence coverage.
- Answer to the project question.
- Implications and interventions.
- Confidence assessment.
- Open questions and next steps.

## A model of several types

When a model is several types at once (a loop map with a simulation and a network on the same map), the reader-facing sections — the answer, implications, confidence and open questions — are **one set for the whole model**: their claims pool every type's, each labelled by where it came from ("Simulation: …", "Network: …"). The technical sections (structure, key findings, sensitivity, assumptions, evidence) stay one per type, and describe only that type's own factors and links. When a model gains a second type, any answer already written is kept as the model-wide answer (earlier versions stay in its history).

## Workflow

1. Initialise or refresh interpretation sections.
2. Refresh claims from current project state.
3. Generate prose for each section.
4. Edit prose where needed.
5. Use the generated sections in Communicate.

## How the claims are counted

- **Evidence coverage** counts links (the model's claims) that have at least one source; factors aren't counted.
- **Intervention points** are factors many causal paths run through. The outcome the model explains is left out once it's marked: `latris view role cld "<factor>" outcome`.
- **Feedback loops** are counted as mechanisms: two cycles that differ by one alternative step count once.

## Keep it current

If the model changes after prose is generated, refresh claims and regenerate affected sections before exporting.

In client and publication reports the answer, implications and confidence come first.
