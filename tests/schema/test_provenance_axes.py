"""Tests for M11 provenance axes: ProvenanceOrigin, ProvenanceVerification,
ExpertActor, and the source_id pattern.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from latris.schema import (
    AIActor,
    ExpertActor,
    HumanActor,
    Informants,
    QuoteLocation,
)
from latris.schema.attributes import (
    DescriptionEntry,
    EvidenceLink,
)
from latris.schema.substrate import Edge, Entity

# -- ProvenanceOrigin / ProvenanceVerification defaults --


def test_entity_defaults_human_direct_unverified():
    e = Entity(id="node_01TEST", kind="variable", label="X")
    assert e.origin == "human-direct"
    assert e.verification == "unverified"
    assert e.source_id is None


def test_edge_defaults_human_direct_unverified():
    e = Edge(id="edge_01TEST", from_id="a", to_id="b")
    assert e.origin == "human-direct"
    assert e.verification == "unverified"
    assert e.source_id is None


def test_description_entry_defaults():
    d = DescriptionEntry(target_id="x", value="Some description.")
    assert d.origin == "human-direct"
    assert d.verification == "unverified"
    assert d.source_id is None


def test_evidence_link_defaults():
    """EvidenceLink no longer carries the vestigial `verification` field
    or `reviewed_by_human` flag (Phase 1 of the AI interrogation layer).
    The new audit axes are verified_by, source_access, support_verdict,
    quote, and quote_location."""
    e = EvidenceLink(target_id="x", attribute="polarity", bibkey="ref1")
    assert e.origin == "human-direct"
    assert e.source_id is None
    # New axes — conservative defaults.
    assert e.verified_by == "human"
    assert e.source_access == "title_only"
    assert e.support_verdict == "unverified"
    assert e.quote is None
    assert e.quote_location is None


# -- Setting non-default provenance values --


def test_entity_with_data_derived_origin():
    e = Entity(
        id="node_01TEST",
        kind="variable",
        label="Learned",
        origin="data-derived",
        verification="human-verified",
        source_id="analysis-run_01ABC",
    )
    assert e.origin == "data-derived"
    assert e.verification == "human-verified"
    assert e.source_id == "analysis-run_01ABC"


def test_edge_with_ai_proposed_origin():
    e = Edge(
        id="edge_01TEST",
        from_id="a",
        to_id="b",
        origin="ai-proposed",
        verification="ai-verified",
        source_id="interaction_01ABC",
    )
    assert e.origin == "ai-proposed"
    assert e.verification == "ai-verified"


def test_description_with_human_elicited_origin():
    d = DescriptionEntry(
        target_id="x",
        value="Elicited.",
        origin="human-elicited",
        verification="human-verified",
        source_id="elicitation_01ABC",
    )
    assert d.origin == "human-elicited"
    assert d.source_id == "elicitation_01ABC"


# -- Invalid provenance values rejected --


def test_invalid_origin_rejected():
    with pytest.raises(ValidationError):
        Entity(id="node_01TEST", kind="variable", label="X", origin="invalid-origin")


def test_invalid_verification_rejected():
    with pytest.raises(ValidationError):
        Entity(id="node_01TEST", kind="variable", label="X", verification="magic")


# -- ExpertActor --


def test_expert_actor_creation():
    expert = ExpertActor(
        name="Dr. Jones",
        email="jones@uni.edu",
        credentials="PhD statistics",
        affiliation="MIT",
        calibration_score=0.92,
    )
    assert expert.kind == "expert"
    assert expert.name == "Dr. Jones"
    assert expert.calibration_score == 0.92


def test_expert_actor_minimal():
    expert = ExpertActor(name="Expert A")
    assert expert.kind == "expert"
    assert expert.email is None
    assert expert.credentials is None
    assert expert.calibration_score is None


# -- ExpertActor in Informants --


def test_expert_in_informants_proposed_by():
    expert = ExpertActor(name="Dr. Jones")
    human = HumanActor(name="Alice")
    ai = AIActor(model_id="claude-opus-4-6")
    info = Informants(
        proposed_by=[expert, human],
        approved_by=[ai],
    )
    assert len(info.proposed_by) == 2
    assert info.proposed_by[0].kind == "expert"
    assert info.proposed_by[1].kind == "human"


def test_expert_in_description_entry_informants():
    expert = ExpertActor(name="Dr. Jones", credentials="MD")
    entry = DescriptionEntry(
        target_id="node_01",
        value="Expert view.",
        informants=Informants(proposed_by=[expert]),
        origin="human-elicited",
    )
    assert entry.informants.proposed_by[0].kind == "expert"
    assert entry.origin == "human-elicited"


# -- All origin values accepted --


@pytest.mark.parametrize(
    "origin",
    [
        "human-direct",
        "human-elicited",
        "ai-proposed",
        "data-derived",
        "imported",
        "mixed",
    ],
)
def test_all_origin_values_accepted(origin):
    e = Entity(id="node_01TEST", kind="concept", label="X", origin=origin)
    assert e.origin == origin


@pytest.mark.parametrize(
    "verification",
    [
        "unverified",
        "ai-verified",
        "human-verified",
    ],
)
def test_all_verification_values_accepted(verification):
    e = Entity(id="node_01TEST", kind="concept", label="X", verification=verification)
    assert e.verification == verification


# -- AI interrogation Phase 1: EvidenceLink audit axes --


@pytest.mark.parametrize(
    "source_access",
    ["title_only", "abstract", "full_text_chunk", "full_text"],
)
def test_all_source_access_values_accepted(source_access):
    link = EvidenceLink(
        target_id="x", attribute="polarity", bibkey="ref1", source_access=source_access
    )
    assert link.source_access == source_access


@pytest.mark.parametrize(
    "verdict",
    ["unverified", "supports", "contradicts", "orthogonal", "insufficient_extract"],
)
def test_all_support_verdict_values_accepted(verdict):
    link = EvidenceLink(
        target_id="x", attribute="polarity", bibkey="ref1", support_verdict=verdict
    )
    assert link.support_verdict == verdict


def test_invalid_source_access_rejected():
    with pytest.raises(ValidationError):
        EvidenceLink(target_id="x", attribute="polarity", bibkey="ref1", source_access="hearsay")


def test_invalid_support_verdict_rejected():
    with pytest.raises(ValidationError):
        EvidenceLink(target_id="x", attribute="polarity", bibkey="ref1", support_verdict="probably")


def test_evidence_link_with_full_audit_trail():
    """An evidence link with the full audit trail Phase 4 will produce:
    AI proposer, full-text chunk seen, claim verified by verbatim quote
    at a known chunk + page + offset."""
    link = EvidenceLink(
        target_id="edge_01ABC",
        attribute="polarity",
        bibkey="smith2023",
        verified_by="ai",
        source_access="full_text_chunk",
        support_verdict="supports",
        quote="Lower prices increase demand in liquid markets.",
        quote_location=QuoteLocation(
            chunk_hash="sha256:abc123",
            page=12,
            offset=440,
        ),
    )
    assert link.verified_by == "ai"
    assert link.source_access == "full_text_chunk"
    assert link.support_verdict == "supports"
    assert link.quote_location is not None
    assert link.quote_location.chunk_hash == "sha256:abc123"
    assert link.quote_location.page == 12
    assert link.quote_location.offset == 440


def test_quote_location_chunk_hash_required():
    """QuoteLocation requires a chunk_hash; page and offset are optional."""
    loc = QuoteLocation(chunk_hash="sha256:xyz")
    assert loc.chunk_hash == "sha256:xyz"
    assert loc.page is None
    assert loc.offset is None
    with pytest.raises(ValidationError):
        QuoteLocation()  # type: ignore[call-arg]


def test_evidence_link_rejects_unknown_extra_fields():
    """The pre-Phase-1 fields (`reviewed_by_human`, EvidenceLink-level
    `verification`) are gone; passing them in raises rather than
    silently round-tripping into the YAML."""
    with pytest.raises(ValidationError):
        EvidenceLink(
            target_id="x",
            attribute="polarity",
            bibkey="ref1",
            reviewed_by_human=True,  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        EvidenceLink(
            target_id="x",
            attribute="polarity",
            bibkey="ref1",
            verification="ai-verified",  # type: ignore[call-arg]
        )
