"""Tests for cross-store coherence checks."""

from dataclasses import dataclass

from latris.operations.coherence_checks import (
    CoherenceFinding,
    check_polarity_description_coherence,
)


@dataclass
class _Edge:
    id: str


@dataclass
class _Desc:
    value: str


@dataclass
class _Pol:
    value: str
    source_id: str | None = None


def _stores(edge_id: str, desc: str | None, polarity: str | None, rationale: str | None = None):
    descs = {(edge_id, "description"): _Desc(value=desc)} if desc is not None else {}
    pols = (
        {(edge_id, "polarity"): _Pol(value=polarity, source_id=rationale)}
        if polarity is not None
        else {}
    )
    return descs, pols


def test_no_polarity_no_finding():
    edges = [_Edge("e1")]
    descs, pols = _stores("e1", desc="Increases output.", polarity=None)
    assert check_polarity_description_coherence(edges, descs, pols) == []


def test_no_description_no_finding():
    edges = [_Edge("e1")]
    descs, pols = _stores("e1", desc=None, polarity="+", rationale="trickle through")
    assert check_polarity_description_coherence(edges, descs, pols) == []


def test_aligned_description_and_polarity():
    """Description uses an increase verb, polarity is + — these agree."""
    edges = [_Edge("e1")]
    descs, pols = _stores(
        "e1",
        desc="Higher motivation increases output.",
        polarity="+",
        rationale="more effort, more product",
    )
    assert check_polarity_description_coherence(edges, descs, pols) == []


def test_decrease_verb_with_positive_polarity_flagged():
    """The 4DWW edge bug: 'reduces stress' but polarity '+'."""
    edges = [_Edge("e1")]
    descs, pols = _stores(
        "e1",
        desc="Good client coverage reduces stress from rework.",
        polarity="+",
        rationale="anything",
    )
    findings = check_polarity_description_coherence(edges, descs, pols)
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, CoherenceFinding)
    assert f.target_id == "e1"
    assert f.severity == "likely"
    assert f.kind == "polarity_description_conflict"


def test_increase_verb_with_negative_polarity_flagged():
    edges = [_Edge("e1")]
    descs, pols = _stores(
        "e1",
        desc="Compressed weeks increase intensity.",
        polarity="-",
        rationale="anything",
    )
    findings = check_polarity_description_coherence(edges, descs, pols)
    assert len(findings) == 1
    assert findings[0].severity == "likely"


def test_ambiguous_polarity_skipped():
    """Polarity '~' is by definition not directional; no lint."""
    edges = [_Edge("e1")]
    descs, pols = _stores(
        "e1",
        desc="Reduces stress.",
        polarity="~",
        rationale="non-monotonic",
    )
    assert check_polarity_description_coherence(edges, descs, pols) == []


def test_opposing_verbs_in_description_and_rationale_possible_conflict():
    """4DWW's actual case: description 'reduces stress' + rationale 'drains staff'.

    Description says decrease, rationale says decrease too — but with
    opposite framing (one is positive-on-target, the other is
    negative-on-target). For our verb heuristic, 'drain' is a decrease
    verb, so this specific case won't trip the *possible* branch — it's
    actually consistent at the verb level. The 'possible' branch fires
    when description and rationale use truly opposing verb classes.
    """
    edges = [_Edge("e1")]
    # Polarity '+' rationale 'reduces' contradicts description that 'increases'
    descs, pols = _stores(
        "e1",
        desc="Slow growth accumulates over months.",  # neutral, no verb hit
        polarity="+",
        rationale="actually it reduces the target",
    )
    # Description has no decrease/increase verb so 'likely' branch doesn't fire.
    # Rationale has 'reduces' but description has neither — no 'possible' either.
    assert check_polarity_description_coherence(edges, descs, pols) == []


def test_opposing_verb_classes_flag_possible():
    edges = [_Edge("e1")]
    descs, pols = _stores(
        "e1",
        desc="Boosts engagement.",
        polarity="+",
        rationale="actually it reduces motivation in the long run",
    )
    findings = check_polarity_description_coherence(edges, descs, pols)
    # Description 'boosts' (+verb) aligns with polarity '+', so likely
    # branch is skipped. Rationale 'reduces' (-verb) opposes description
    # (+verb) — possible branch fires.
    assert len(findings) == 1
    assert findings[0].severity == "possible"


def test_multiple_edges_independent():
    edges = [_Edge("e1"), _Edge("e2"), _Edge("e3")]
    descs = {
        ("e1", "description"): _Desc(value="Reduces stress."),
        ("e2", "description"): _Desc(value="Increases output."),
        ("e3", "description"): _Desc(value="Stays flat."),
    }
    pols = {
        ("e1", "polarity"): _Pol(value="+", source_id=""),
        ("e2", "polarity"): _Pol(value="+", source_id=""),
        ("e3", "polarity"): _Pol(value="+", source_id=""),
    }
    findings = check_polarity_description_coherence(edges, descs, pols)
    flagged = {f.target_id for f in findings}
    assert flagged == {"e1"}
