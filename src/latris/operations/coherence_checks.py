"""Cross-store coherence checks (pure functions, no I/O).

Detects contradictions between independently-authored attribute stores —
for instance, an edge whose substrate description says "high coverage
reduces stress" (positive on the target) but whose polarity rationale
in the CLD view says "high coverage drains staff" (negative). The two
stores are populated by different prompts at different times, so the
contradictions surfaced by this check are real defects, not just style
mismatches.

Pure-function style matches `operations/_graph_checks.py`. Callers load
the substrate + attribute stores and pass them in; this module never
reads YAML directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Verbs that signal a *decrease* in the target. Description with one of
# these → if polarity is "+" we have a likely contradiction.
_DECREASE_VERBS = frozenset(
    {
        "reduce",
        "reduces",
        "reducing",
        "reduced",
        "decrease",
        "decreases",
        "decreasing",
        "decreased",
        "lower",
        "lowers",
        "lowering",
        "lowered",
        "mitigate",
        "mitigates",
        "mitigating",
        "mitigated",
        "prevent",
        "prevents",
        "preventing",
        "prevented",
        "inhibit",
        "inhibits",
        "inhibiting",
        "inhibited",
        "suppress",
        "suppresses",
        "suppressing",
        "suppressed",
        "drain",
        "drains",
        "draining",
        "drained",
        "undermine",
        "undermines",
        "undermining",
        "undermined",
    }
)

# Verbs that signal an *increase* in the target. Description with one of
# these → if polarity is "-" we have a likely contradiction.
_INCREASE_VERBS = frozenset(
    {
        "increase",
        "increases",
        "increasing",
        "increased",
        "raise",
        "raises",
        "raising",
        "raised",
        "boost",
        "boosts",
        "boosting",
        "boosted",
        "amplify",
        "amplifies",
        "amplifying",
        "amplified",
        "drive",
        "drives",
        "driving",
        "driven",
        "strengthen",
        "strengthens",
        "strengthening",
        "strengthened",
        "enhance",
        "enhances",
        "enhancing",
        "enhanced",
        "improve",
        "improves",
        "improving",
        "improved",
        "grow",
        "grows",
        "growing",
        "grew",
    }
)


@dataclass(frozen=True)
class CoherenceFinding:
    """A detected contradiction between two attribute stores."""

    target_id: str
    kind: Literal["polarity_description_conflict"]
    description: str
    polarity: str
    polarity_rationale: str
    severity: Literal["likely", "possible"]
    reason: str


def _classify_verbs(text: str) -> tuple[bool, bool]:
    """Return (has_decrease_verb, has_increase_verb) for the given text."""
    if not text:
        return (False, False)
    # Normalise: lowercase, strip punctuation. Splitting on word boundaries
    # is good enough for this lint — false positives are noisier than
    # missed cases, so the verb lists are deliberately narrow.
    tokens = {
        w.strip(".,;:!?()[]\"'`").lower()
        for w in text.split()
    }
    return (
        bool(tokens & _DECREASE_VERBS),
        bool(tokens & _INCREASE_VERBS),
    )


def check_polarity_description_coherence(
    edges,
    descriptions: dict,
    polarities: dict,
) -> list[CoherenceFinding]:
    """Find edges whose description and polarity tell opposite stories.

    Parameters:
        edges: iterable of Edge objects (each with at least .id).
        descriptions: mapping (target_id, "description") → DescriptionEntry
            (matches the lookup shape already used in exporters/markdown.py).
        polarities: mapping (target_id, "polarity") → PolarityEntry.

    Returns a list of CoherenceFinding. Empty list = no contradictions
    detected. An edge with no polarity OR no description yields no finding.
    """
    findings: list[CoherenceFinding] = []
    for edge in edges:
        desc_entry = descriptions.get((edge.id, "description"))
        pol_entry = polarities.get((edge.id, "polarity"))
        if desc_entry is None or pol_entry is None:
            continue

        desc_text = desc_entry.value or ""
        polarity_value = pol_entry.value
        # Prefer the dedicated rationale field (co-authored with the polarity);
        # fall back to source_id for entries written before that field existed.
        rationale = getattr(pol_entry, "rationale", None) or pol_entry.source_id or ""

        # The ambiguous polarity intentionally doesn't carry a directional
        # story, so we can't lint it against the description.
        if polarity_value not in ("+", "-"):
            continue

        desc_has_decrease, desc_has_increase = _classify_verbs(desc_text)
        rat_has_decrease, rat_has_increase = _classify_verbs(rationale)

        # Likely conflict: description verb directly contradicts the polarity sign.
        if desc_has_decrease and not desc_has_increase and polarity_value == "+":
            findings.append(
                CoherenceFinding(
                    target_id=edge.id,
                    kind="polarity_description_conflict",
                    description=desc_text,
                    polarity=polarity_value,
                    polarity_rationale=rationale,
                    severity="likely",
                    reason=(
                        "Description uses a *decrease* verb on the target "
                        "but polarity is '+'. The polarity rationale must "
                        "tell the same causal story as the description."
                    ),
                )
            )
            continue
        if desc_has_increase and not desc_has_decrease and polarity_value == "-":
            findings.append(
                CoherenceFinding(
                    target_id=edge.id,
                    kind="polarity_description_conflict",
                    description=desc_text,
                    polarity=polarity_value,
                    polarity_rationale=rationale,
                    severity="likely",
                    reason=(
                        "Description uses an *increase* verb on the target "
                        "but polarity is '-'. The polarity rationale must "
                        "tell the same causal story as the description."
                    ),
                )
            )
            continue

        # Possible conflict: description and polarity rationale use
        # opposing verbs. This catches cases like the 4DWW edge where
        # description said "reduces stress" but rationale said "drains
        # staff" — same direction phrased oppositely.
        if (desc_has_decrease and rat_has_increase) or (
            desc_has_increase and rat_has_decrease
        ):
            findings.append(
                CoherenceFinding(
                    target_id=edge.id,
                    kind="polarity_description_conflict",
                    description=desc_text,
                    polarity=polarity_value,
                    polarity_rationale=rationale,
                    severity="possible",
                    reason=(
                        "Description and polarity rationale use opposing "
                        "directional verbs. They may be telling opposite "
                        "causal stories for the same edge."
                    ),
                )
            )

    return findings
