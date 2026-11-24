"""Guidance blocks shared by several prompt templates."""

from __future__ import annotations

# ---------- Shared guidance blocks ----------
#
# These constants are interpolated into multiple prompt templates so that
# tightening guidance in one place can't silently leave a duplicate behind.
# Keep them tightly worded — they appear verbatim in user-facing prompts.

_MECHANISTIC_GRANULARITY_GUIDANCE = (
    "MECHANISTIC GRANULARITY: prefer specific, measurable, intervenable "
    "variables over broad trends or framings. A good variable is the "
    "lever, flow, stock, or quantity someone could in principle "
    "observe or act on.\n"
    "Examples (good → bad):\n"
    "  good: 'phosphorus loading', 'fertiliser application rate', "
    "'riparian vegetation cover', 'mean residence time'\n"
    "  bad:  'agricultural trends', 'land-use pressure', "
    "'ecosystem health', 'environmental concerns'\n"
    "If a candidate is a category or trend, decompose it into the "
    "underlying mechanistic drivers and produce those instead."
)


_LOOP_CLOSURE_GUIDANCE = (
    "LOOP CLOSURE (CLDs only): when the project is configured as a CLD, "
    "the user message will include a loop-closure-guidance block listing "
    "current loops and candidate closure pairs. CLDs are defined by "
    "feedback structure — if 0 or 1 loops are detected, you MUST "
    "propose at least one reinforcing and one balancing loop with a "
    "named mechanism, using the candidate pairs as starting points. "
    "Name in each rationale which loop a new edge participates in."
)


_EXISTENCE_ATTRIBUTE_CONVENTIONS = (
    "Attribute conventions:\n"
    "  'existence' — the reference supports that this entity or edge "
    "belongs in the model (its presence is empirically grounded). Prefer "
    "this when citing evidence for an entity or edge as a whole.\n"
    "  'description', 'polarity', 'confidence', etc. — the reference "
    "specifically supports that named field of the target. Use these "
    "narrower attributes when the evidence is field-specific."
)


_EXISTENCE_ATTRIBUTE_DEFAULT_NOTE = (
    "Default attribute is 'existence' (the reference supports the "
    "element as a whole); use a narrower attribute only when the "
    "evidence is field-specific."
)


_NO_FABRICATION_GUIDANCE = (
    "Do NOT fabricate content not present in the supplied evidence or "
    "project context — no invented references, URLs, quotes, variables, "
    "or claims. If you cannot find adequate evidence, say so rather "
    "than inventing."
)


_NODE_KIND_RUBRIC = (
    "NODE KIND — assign the most specific kind that fits; do NOT default "
    "everything to 'concept'. Choose exactly one:\n"
    "  variable — a measurable or observable quantity that can rise or fall "
    "(e.g. 'weekly hours worked', 'applicants per opening'). PREFER THIS "
    "whenever the node is something you could in principle measure.\n"
    "  concept — an abstract driver or construct with no direct measure "
    "(e.g. 'organisational culture'). Use only when no measurable proxy fits.\n"
    "  event — a discrete occurrence at a point in time (e.g. 'policy launch').\n"
    "  actor — a person, organisation, or agent that acts (e.g. 'key client').\n"
    "  state — a condition that holds over a period (e.g. 'understaffed').\n"
    "  decision — a deliberate choice an actor controls (e.g. 'adopt four-day week').\n"
    "  hazard — a threat or adverse possibility (e.g. 'loss of a key client').\n"
    "If genuinely none fit, use 'concept' and note why in the description. "
    "Never invent a kind outside this list."
)


_NODE_FEWSHOT = (
    "<examples>\n"
    "  <example>\n"
    "    context: model about adopting a four-day work week\n"
    "    good: 'weekly hours worked' (variable), 'applicants per opening' "
    "(variable), 'voluntary attrition rate' (variable), 'adopt four-day "
    "week' (decision)\n"
    "    bad:  'Employee Well-being' (concept), 'Recruitment Strength' "
    "(concept), 'Productivity' (concept)\n"
    "    why:  the bad items are broad framings dumped as 'concept'. "
    "Decompose each into the measurable lever that carries the effect — "
    "well-being to 'self-reported burnout score' + 'sick days per month'; "
    "recruitment strength to 'applicants per opening' + 'offer-acceptance rate'.\n"
    "  </example>\n"
    "  <example>\n"
    "    context: coastal water-quality model\n"
    "    good: 'phosphorus loading' (variable), 'fertiliser application rate' "
    "(variable), 'riparian vegetation cover' (variable)\n"
    "    bad:  'agricultural trends', 'ecosystem health', 'land-use pressure'\n"
    "    why:  categories and trends, not levers. Decompose into the "
    "mechanistic quantity someone could observe or act on.\n"
    "  </example>\n"
    "</examples>"
)


_EDGE_MECHANISM_GUIDANCE = (
    "EDGE MECHANISM — each edge is ONE direct causal step. State the "
    "mechanism (how the source changes the target) in the description, not a "
    "restatement of the labels. When an existing node M plausibly sits on the "
    "path from A to Z (A acts on Z *through* M), propose A→M and M→Z rather "
    "than the shortcut A→Z. Prefer a few load-bearing edges over an "
    "exhaustive pairwise sweep."
)


_ENTITY_PROVENANCE_GUIDANCE = (
    "PROVENANCE — capture the reasoning behind each node/edge in the same "
    "proposal, so the model is defensible without a second pass:\n"
    "  assumptions — add an assumption ONLY where the element rests on a "
    "non-obvious premise that, if wrong, would change the model (state it and "
    "why). Do NOT manufacture one per element; most elements need none. An "
    "empty list is the right answer when nothing non-obvious is at stake.\n"
    "  source_bibkeys — when a node or claim is grounded in one of the supplied "
    "references, list that reference's bibkey. Use ONLY bibkeys present in the "
    "supplied evidence; never invent one. Leave empty if the element is "
    "reasoned rather than sourced.\n"
    "  confidence — optionally 'low' / 'medium' / 'high' for how well-supported "
    "the element is."
)


_EDGE_POLARITY_GUIDANCE = (
    "EDGE POLARITY (CLDs) — when the project is a CLD, give each causal edge a "
    "polarity and a one-line polarity_rationale, authored together with the "
    "description so they cannot drift:\n"
    "  polarity — '+' if the source increases the target (or both move the "
    "same way), '-' if the source decreases it (they move oppositely), '~' if "
    "genuinely non-monotonic or contested.\n"
    "  polarity_rationale MUST tell the SAME causal story as the description. "
    "If you think the description's direction is wrong, do NOT silently invert "
    "the polarity — set the polarity that matches the description, mark "
    "confidence='low', and flag the disagreement in the rationale so a human "
    "can reconcile both. Leave polarity empty for non-CLD projects or "
    "non-causal edge kinds."
)


_SCOPE_CONTRACT_GUIDANCE = (
    "SCOPE CONTRACT — the project context may declare coverage dimensions, a "
    "granularity level, and an intended audience. When present, treat them as "
    "binding:\n"
    "  - Coverage dimensions: the model MUST span EVERY listed dimension — do "
    "not omit one, and do not stray far outside them. This is what keeps "
    "repeated runs covering the same ground.\n"
    "  - Granularity level: every node must match the stated level of "
    "resolution (e.g. a specific measurable variable vs a broad theme) and the "
    "abstraction level must stay UNIFORM across the whole model.\n"
    "  - Audience: frame the variables and mechanisms for the stated audience.\n"
    "If a field is absent from the project context, use your own judgement for "
    "that aspect."
)
