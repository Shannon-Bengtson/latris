# Methods and foundations

Latris implements established methods and cites them. It does not invent a new
causal calculus, a new simulation algorithm, or a new theory of evidence — it
implements well-known ones, records which were used in each project, and states
their limits next to their results. This page is the map: for each formalism,
the literature it stands on, what Latris actually implements (with the command
or module that implements it), and what it deliberately does not do.

**The citation rule.** A work is cited only where Latris implements the method
it describes — not the whole book, and never a method that is only planned.
Where Latris borrows an idea as inspiration rather than implementation, the
text says so. If you find a citation here that overclaims, that is a bug:
please report it.

**One substrate, several formalisms.** Every model type in Latris shares the
same evidentiary substrate: links are claims, claims carry sources, sources
are checked against what they are claimed to support, and disagreement is
recorded rather than resolved silently. The formalisms below differ in what
kind of reasoning they support; the evidence discipline does not.

## Causal loop diagrams (qualitative)

- **Lineage.** Sterman (2000), *Business Dynamics*, ch. 4 — the canonical
  treatment of causal loop diagrams and loop polarity. Meadows (2008),
  *Thinking in Systems* — the accessible statement of the same tradition.
- **Implemented.** Loop detection by Johnson's (1975) elementary-circuits
  algorithm (`latris analyse loops`); polarity classification (an odd count of
  `−` edges makes a balancing loop); qualitative effect propagation along
  paths (`operations/graph_analysis.py`).
- **Limits.** A polarity of `~` (ambiguous) is reported as "unknown", not
  guessed. Loop enumeration is capped; beyond the cap Latris raises
  `TooManyLoops` rather than silently sampling. Decision-rule, governance and
  definitional edges are excluded from loop and centrality analysis — they
  are policy or identity links, not feedback mechanisms.

## Causal DAGs — identification, not estimation

- **Lineage.** Pearl (2009), *Causality*; Pearl & Mackenzie (2018), *The Book
  of Why*; Hernán & Robins (2020), *Causal Inference: What If*. The
  d-separation test follows Shachter (1998), "Bayes-Ball".
- **Implemented.** d-separation queries, Markov blankets, path enumeration
  (with chain/fork/collider classification), and backdoor adjustment sets by
  graph surgery — the exposure's outgoing edges removed, then testing which
  sets d-separate exposure from outcome (`latris analyse`, DAG-scoped).
- **Limits — read this before citing Pearl.** Latris answers the
  *identification* question only: what would have to be measured (conditioned
  on) for an effect to be estimable. There is no do-operator estimation, no
  g-computation, and no counterfactual computation anywhere in the package.
  Adjustment sets are enumerated only up to size 3; if no valid set of three
  or fewer exists, Latris says so instead of searching further. Analyses run
  on the causal-edge subgraph only.

## Bayesian networks

- **Lineage.** Pearl (1988), *Probabilistic Reasoning in Intelligent Systems*
  — the founding text. Fenton & Neil (2018), *Risk Assessment and Decision
  Analysis with Bayesian Networks* (2nd ed.) — the closest in spirit to
  Latris: expert-elicited structure, defensible numbers, argued cases.
- **Implemented.** Exact inference by variable elimination (pgmpy), per-node
  posterior marginals; Noisy-OR canonical models (binary nodes); CPT parameter
  learning from data (MLE / Bayesian-Dirichlet estimators) with
  human-elicited rows protected from overwrite and learned rows marked
  `data-derived`; one-way (tornado) sensitivity of a target node over CPT
  cells, with a provenance overlay (`latris bn …`).
- **Limits.** Variable elimination only — no junction tree or belief
  propagation. Marginals, not joints. Noisy-OR requires binary nodes and
  parents. Sensitivity is one-way; there is no multi-way or derivative-based
  analysis, and no PSA/EVPI (deferred). Structure learning is excluded by
  design — see `latris capabilities`, `excluded_by_design`.

## Fuzzy cognitive maps

- **Lineage.** Kosko (1986), "Fuzzy Cognitive Maps", *International Journal
  of Man-Machine Studies* 24(1) — weighted matrix iteration to a steady state.
- **Implemented.** `A ← f(A·W)` iterated to convergence with sigmoid (default),
  tanh-rescaled, or step transfer functions; clamped scenario nodes; weights
  validated to [−1, +1] (`latris fcm …`).
- **Limits.** Fixed-point analysis only. A run that does not converge is
  flagged `converged=False`; limit cycles are not detected or classified.

## System dynamics

- **Lineage.** Forrester (1961), *Industrial Dynamics*; Sterman (2000),
  *Business Dynamics*; Meadows (2008). Loop dominance follows the Loops That
  Matter method — Schoenberg, Davidsen & Eberlein (2020), *System Dynamics
  Review* — with the revised flow-to-stock link score of Schoenberg, Hayward &
  Eberlein (2023), the approach Stella and pysimlin ship.
- **Implemented.** Stock-and-flow simulation with dimensional analysis (pint;
  custom base dimensions for person, dollar, item): fixed-step forward Euler,
  or adaptive RK23/RK45; STEP, RAMP, PULSE, TABLE and arithmetic builtins;
  unit-checked scenario overrides with provenance (`latris sd …`); uncertainty
  by seeded Latin-hypercube sampling (McKay, Beckman & Conover 1979) with
  percentile bands and Spearman rank correlations; one-at-a-time sensitivity;
  per-step loop dominance scores with dominant loops flagged
  (`latris sd loops`).
- **Limits.** The adaptive RK option is `solve_ivp` RK45 with a step cap — not
  the classical fixed-step RK4 of Vensim/Stella. Loop dominance enumerates
  loops exhaustively (Johnson's algorithm) up to a cap of 500; larger models
  would need the strongest-path search, which is not implemented. Scores are
  zero whenever stocks stop changing — the method explains change, not
  equilibrium. Monte Carlo is capped at 1000 runs and reports rank
  correlations only.

## The evidence discipline

- **Lineage.** The substrate's vocabulary — claims, warrants, rebuttals — is
  Toulmin's (1958), *The Uses of Argument*. The wider tradition of marshalling
  evidence for and against a claim includes Wigmore (1937) and Schum (1994).
  The practice of recording *which part of a source was read* and *whether it
  supports the claim* follows the evidence-assessment tradition of Bradford
  Hill (1965) and the grading of evidence quality in GRADE (Guyatt et al.
  2008). These are inspirations for the audit trail, not implemented
  criteria: Latris does not score a link against the Bradford Hill checklist,
  and it does not assign GRADE ratings.
- **Implemented.** Source-vs-claim checks with verdicts
  (`latris evidence check`: supports / contradicts / orthogonal /
  insufficient extract); an AI's check must quote the source and the quote is
  looked up in the text Latris holds (`latris ref snapshot`) — a paraphrase
  is refused; every check records who made it and the source's access tier
  (title, abstract, extract, full text). Contested links keep sources for and
  against on the same link and report both. Challenges are an adversarial
  review log with a conversation and a terminal state.
- **Limits.** A Toulmin/IBIS argument-map model type is registered
  (`latris capabilities` lists it) but not planned; the substrate borrows the
  vocabulary, it does not implement the formalism. Checks are only as good as
  the stored source text — a check against an abstract cannot speak for the
  full text.

## Where each formalism sits on the ladder of causation

Pearl & Mackenzie (2018) order causal questions as association → intervention
→ counterfactual. Honest placement:

| Formalism | Position |
|---|---|
| CLD | Mechanism claims — qualitative structure only; arrows are argued, not estimated |
| FCM | Semi-quantitative simulation of the claimed mechanism |
| SD | Quantitative mechanism simulation; scenario analysis intervenes *on the model* |
| DAG / BN | Observational queries and identification — what to measure; no interventional estimation |

A CLD arrow is not a structural equation and carries no do-semantics; a
successful scenario run says what the model does under an assumed change, not
what the world would do. Reports should be quoted with that in mind — and
Latris reports say it themselves in the Methods section.

## Deliberately not implemented

Black-box machine learning and opaque structure learning (they fail the
inspectability test — `latris capabilities`, `excluded_by_design`);
interventional and counterfactual estimation on DAGs; XMILE/Vensim import
(off the roadmap). See the capability manifest for the living list.

## Machine-readable source of truth

The report's **Methods and foundations** section and the capability manifest's
`foundations` block are generated from the same registry,
`latris.operations.foundations` (`latris foundations --json` for the raw
list). This page is the prose companion; if the two disagree, the registry and
the code it describes win, and this page is wrong.

## References

- Bradford Hill, A. (1965). "The Environment and Disease: Association or
  Causation?" *Proceedings of the Royal Society of Medicine*, 58(5), 295–300.
- Fenton, N., & Neil, M. (2018). *Risk Assessment and Decision Analysis with
  Bayesian Networks* (2nd ed.). CRC Press.
- Forrester, J. W. (1961). *Industrial Dynamics*. MIT Press.
- Guyatt, G., et al. (2008). "GRADE: an emerging consensus on rating quality
  of evidence and strength of recommendations." *BMJ*, 336, 924–926.
- Hernán, M., & Robins, J. (2020). *Causal Inference: What If*. Chapman &
  Hall/CRC. <https://hsph.harvard.edu/causalinference/>
- Johnson, D. B. (1975). "Finding all the elementary circuits of a directed
  graph." *SIAM Journal on Computing*, 4(1), 77–84.
- Kosko, B. (1986). "Fuzzy Cognitive Maps." *International Journal of
  Man-Machine Studies*, 24(1), 65–75.
- McKay, M. D., Beckman, R. J., & Conover, W. J. (1979). "A Comparison of
  Three Methods for Selecting Values of Input Variables in the Analysis of
  Output from a Computer Code." *Technometrics*, 21(2), 239–245.
- Meadows, D. H. (2008). *Thinking in Systems: A Primer*. Chelsea Green.
- Pearl, J. (1988). *Probabilistic Reasoning in Intelligent Systems: Networks
  of Plausible Inference*. Morgan Kaufmann.
- Pearl, J. (2009). *Causality: Models, Reasoning and Inference* (2nd ed.).
  Cambridge University Press.
- Pearl, J., & Mackenzie, D. (2018). *The Book of Why: The New Science of
  Cause and Effect*. Basic Books.
- Schum, D. A. (1994). *Evidential Foundations of Probabilistic Reasoning*.
  Wiley.
- Schoenberg, S., Davidsen, P., & Eberlein, R. (2020). "Loops That Matter."
  *System Dynamics Review*.
- Schoenberg, S., Hayward, J., & Eberlein, R. (2023). Revised flow-to-stock
  link score for Loops That Matter. *System Dynamics Review*.
- Shachter, R. D. (1998). "Bayes-Ball: The Rational Pastime." *Proceedings of
  the 14th Conference on Uncertainty in Artificial Intelligence (UAI)*.
- Sterman, J. D. (2000). *Business Dynamics: Systems Thinking and Modeling
  for a Complex World*. Irwin/McGraw-Hill.
- Toulmin, S. E. (1958). *The Uses of Argument*. Cambridge University Press.
- Wigmore, J. H. (1937). *The Science of Judicial Proof* (3rd ed.). Little,
  Brown.
