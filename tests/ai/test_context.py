"""Tests for AI context assembly — helpers and builder dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import attributes as attr_ops
from latris.operations import challenges as ch_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths
from latris.schema import Substrate
from tests.conftest import build_with_template_identity, clone_project


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")


@pytest.fixture(scope="module")
def _module_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """init + Price + Demand + edge + polarity (-) + Price description.

    Statement is "What drives demand?" — line 145 asserts on it.
    """

    def build() -> Path:
        root = tmp_path_factory.mktemp("ai_context_tpl") / "proj"
        init_project(root, statement="What drives demand?")
        a, _ = node_ops.add_node("Price", kind="variable", root=root)
        b, _ = node_ops.add_node("Demand", kind="variable", root=root)
        edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
        view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)
        attr_ops.set_attribute(a.id, "description", "Market price level", root=root)
        return root

    return build_with_template_identity(build)


@pytest.fixture
def populated_project(_module_template: Path, tmp_path: Path, git_identity) -> ProjectPaths:
    return ProjectPaths(clone_project(_module_template, tmp_path / "proj"))


# ── Helper functions ─────────────────────────────────────────────────


def test_neighbours_of_node(populated_project) -> None:
    from latris.ai.context import _neighbours_of_node
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, populated_project.conceptual_yaml)
    price = next(e for e in sub.entities if e.label == "Price")
    demand = next(e for e in sub.entities if e.label == "Demand")

    neighbours = _neighbours_of_node(sub, price.id)
    assert len(neighbours["outbound"]) == 1
    assert neighbours["outbound"][0]["to_id"] == demand.id
    assert len(neighbours["inbound"]) == 0

    neighbours_demand = _neighbours_of_node(sub, demand.id)
    assert len(neighbours_demand["inbound"]) == 1
    assert neighbours_demand["inbound"][0]["from_id"] == price.id


def test_attributes_for(populated_project) -> None:
    from latris.ai.context import _attributes_for
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, populated_project.conceptual_yaml)
    price = next(e for e in sub.entities if e.label == "Price")
    edge = sub.edges[0]

    attrs = _attributes_for(populated_project, price.id)
    assert "description" in attrs
    assert attrs["description"]["value"] == "Market price level"

    edge_attrs = _attributes_for(populated_project, edge.id)
    assert "polarity" in edge_attrs
    assert edge_attrs["polarity"]["value"] == "-"


def test_attributes_for_nonexistent_target(populated_project) -> None:
    from latris.ai.context import _attributes_for

    attrs = _attributes_for(populated_project, "node_NONEXISTENT")
    assert attrs == {}


def test_relevant_assumptions_exclusions_empty(populated_project) -> None:
    from latris.ai.context import _relevant_assumptions_exclusions

    result = _relevant_assumptions_exclusions(populated_project)
    assert result["assumptions"] == []
    assert result["exclusions"] == []


def test_existing_challenges_for_target(populated_project) -> None:
    from latris.ai.context import _existing_challenges_for_target
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, populated_project.conceptual_yaml)
    edge = sub.edges[0]
    root = populated_project.root

    # No challenges initially
    challenges = _existing_challenges_for_target(populated_project, edge.id)
    assert challenges == []

    # Open a challenge
    ch_ops.open_challenge(edge.id, "Direction is wrong", root=root)
    challenges = _existing_challenges_for_target(populated_project, edge.id)
    assert len(challenges) == 1
    assert challenges[0]["state"] == "open"
    assert "Direction is wrong" in challenges[0]["argument"]


# ── build_context dispatch ───────────────────────────────────────────


def test_build_context_explain(populated_project) -> None:
    from latris.ai.context import build_context
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, populated_project.conceptual_yaml)
    price = next(e for e in sub.entities if e.label == "Price")

    pack = build_context("ExplainThisElement", {"target_id": price.id}, populated_project)
    assert pack.system  # non-empty
    assert pack.user  # non-empty
    assert "Price" in pack.user
    assert price.id in pack.target_ids


def test_build_context_challenge(populated_project) -> None:
    from latris.ai.context import build_context
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, populated_project.conceptual_yaml)
    edge = sub.edges[0]

    pack = build_context("ChallengeThisConnection", {"target_id": edge.id}, populated_project)
    assert pack.system
    assert pack.user
    assert edge.id in pack.target_ids


def test_build_context_draft(populated_project) -> None:
    from latris.ai.context import build_context

    pack = build_context("DraftConceptualModel", {}, populated_project)
    assert pack.system
    assert pack.user
    assert "demand" in pack.user.lower() or "What drives demand" in pack.user


def test_build_context_scope_check(populated_project) -> None:
    from latris.ai.context import build_context

    pack = build_context("ScopeCheck", {}, populated_project)
    assert pack.system
    assert pack.user


def test_build_context_find_connections(populated_project) -> None:
    from latris.ai.context import build_context

    pack = build_context("FindNewConnections", {}, populated_project)
    assert pack.system
    assert pack.user


def test_build_context_unknown_prompt_raises(populated_project) -> None:
    from latris.ai.context import build_context

    with pytest.raises(ValueError, match="no context builder"):
        build_context("NonexistentPrompt", {}, populated_project)


# ── Format helpers ───────────────────────────────────────────────────


def test_format_block_empty() -> None:
    from latris.ai.context import _format_block

    result = _format_block("Assumptions", [])
    assert "_(none)_" in result


def test_format_block_with_items() -> None:
    from latris.ai.context import _format_block

    result = _format_block("Assumptions", ["A1", "A2"])
    assert "- A1" in result
    assert "- A2" in result
    assert "## Assumptions" in result


def test_format_kv_block() -> None:
    from latris.ai.context import _format_kv_block

    items = [{"id": "c1", "state": "open", "argument": "Disputed"}]
    result = _format_kv_block("Challenges", items)
    assert "id: c1" in result
    assert "state: open" in result


# ── Tag constants ────────────────────────────────────────────────────


def test_tag_constants() -> None:
    from latris.ai.context import APPROVED_TAG, REJECTED_TAG

    assert "REJECTED" in REJECTED_TAG
    assert "APPROVED" in APPROVED_TAG


# ── New provenance prompt context builders ──────────────────────────


@pytest.fixture
def simple_project(tmp_path: Path, git_identity) -> ProjectPaths:
    """Simpler fixture without view attributes for provenance prompt tests."""
    root = tmp_path / "proj2"
    init_project(root, statement="How does pollution affect health?")
    a, _ = node_ops.add_node("Emissions", kind="variable", root=root)
    b, _ = node_ops.add_node("AirQuality", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    attr_ops.set_attribute(a.id, "description", "Industrial emissions", root=root)
    return ProjectPaths(root)


def test_build_context_generate_assumptions(simple_project) -> None:
    from latris.ai.context import build_context
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, simple_project.conceptual_yaml)
    node = next(e for e in sub.entities if e.label == "Emissions")

    pack = build_context("GenerateAssumptions", {"target_id": node.id}, simple_project)
    assert pack.system
    assert pack.user
    assert "Emissions" in pack.user
    assert "AssumptionsProposal" in pack.user
    assert node.id in pack.target_ids


def test_build_context_suggest_decisions(simple_project) -> None:
    from latris.ai.context import build_context
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, simple_project.conceptual_yaml)
    node = next(e for e in sub.entities if e.label == "AirQuality")

    pack = build_context("SuggestDecisions", {"target_id": node.id}, simple_project)
    assert pack.system
    assert pack.user
    assert "AirQuality" in pack.user
    assert "DecisionsProposal" in pack.user
    assert node.id in pack.target_ids


def test_build_context_suggest_exclusions(simple_project) -> None:
    from latris.ai.context import build_context

    pack = build_context("SuggestExclusions", {}, simple_project)
    assert pack.system
    assert pack.user
    assert "Emissions" in pack.user
    assert "ExclusionsProposal" in pack.user


def test_build_context_raise_questions(simple_project) -> None:
    from latris.ai.context import build_context
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, simple_project.conceptual_yaml)
    edge = sub.edges[0]

    pack = build_context("RaiseQuestions", {"target_id": edge.id}, simple_project)
    assert pack.system
    assert pack.user
    assert "QuestionsProposal" in pack.user
    assert edge.id in pack.target_ids


def test_foundation_summary_threads_background(populated_project) -> None:
    """Background appears in the user message of every prompt that takes foundation."""
    from latris.ai.context import _foundation_summary, _load_foundation
    from latris.repo.yaml_io import dump_model

    foundation = _load_foundation(populated_project)
    foundation.background = "Coastal monitoring in Auckland, supporting the 2027 plan."
    foundation.boundary = "Surface-water nutrients only."
    foundation.exclusions = "Air quality."
    dump_model(foundation, populated_project.project_yaml)

    block = _foundation_summary(foundation)
    assert "Background: Coastal monitoring" in block
    assert "Boundary: Surface-water nutrients only." in block
    assert "Exclusions: Air quality." in block
    # Default header
    assert block.startswith("Modelling question:")


def test_foundation_summary_unset_fields_show_placeholder() -> None:
    from latris.ai.context import _foundation_summary
    from latris.schema import ProjectFoundation

    block = _foundation_summary(
        ProjectFoundation(statement="What drives demand?")
    )
    assert "Background: (not set)" in block
    assert "Boundary: (not set)" in block
    assert "Exclusions: (not set)" in block


def test_build_context_fill_provenance_field(populated_project) -> None:
    from latris.ai.context import build_context
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, populated_project.conceptual_yaml)
    node = sub.entities[0]

    pack = build_context(
        "FillProvenanceField",
        {
            "target_kind": "entity",
            "target_id": node.id,
            "field_path": "description",
            "current_value": "",
        },
        populated_project,
    )
    assert pack.system
    assert "Field to fill" in pack.user
    assert "description" in pack.user
    assert node.id in pack.target_ids


def test_build_context_foundational_references_excludes_substrate(populated_project) -> None:
    from latris.ai.context import build_context

    pack = build_context(
        "FindFoundationalReferences", {"focus_area": "lake eutrophication"}, populated_project
    )
    assert "BibliographySearchPlan" in pack.user
    assert "lake eutrophication" in pack.user
    # Foundational mode must NOT include the substrate node labels:
    assert "Price" not in pack.user
    assert "Demand" not in pack.user


def test_build_context_scan_evidence_gaps_includes_substrate(populated_project) -> None:
    from latris.ai.context import build_context

    pack = build_context("ScanEvidenceGaps", {"model_type": "cld"}, populated_project)
    assert "EvidenceGapsScanResult" in pack.user
    # Includes substrate so AI can audit gaps against actual model:
    assert "Price" in pack.user
    assert "Demand" in pack.user


# ── CLD loop-closure guidance ────────────────────────────────────────


@pytest.fixture
def cld_project_no_loop(tmp_path: Path, git_identity) -> ProjectPaths:
    """A project with CLD selected and ≥3 nodes, but no feedback loop yet."""
    from latris.operations.project import update_selected_models

    root = tmp_path / "cld_no_loop"
    init_project(root, statement="Does X reinforce Y?")
    update_selected_models(["cld"], root=root)
    a, _ = node_ops.add_node("A", kind="variable", root=root)
    b, _ = node_ops.add_node("B", kind="variable", root=root)
    node_ops.add_node("C", kind="variable", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    return ProjectPaths(root)


def test_loop_guidance_present_when_cld_selected_no_loops(cld_project_no_loop) -> None:
    """When the project has cld selected and no loops, the connection
    context builders must include loop-closure guidance."""
    from latris.ai.context import build_context

    pack = build_context("FindNewConnections", {}, cld_project_no_loop)
    assert "CLD loop-closure guidance" in pack.user
    assert "NO feedback loops detected" in pack.user
    assert "reinforcing" in pack.user.lower()
    assert "balancing" in pack.user.lower()

    pack2 = build_context(
        "SuggestConnections", {"node_labels": ["A", "B", "C"]}, cld_project_no_loop
    )
    assert "CLD loop-closure guidance" in pack2.user


def test_loop_guidance_absent_when_cld_not_selected(populated_project) -> None:
    """populated_project does not have cld in selected_model_types — guidance
    block must not appear."""
    from latris.ai.context import build_context

    pack = build_context("FindNewConnections", {}, populated_project)
    assert "CLD loop-closure guidance" not in pack.user


def test_loop_guidance_reports_existing_loops(tmp_path: Path, git_identity) -> None:
    """When a loop already exists, the guidance reports its count rather than
    flagging absence."""
    from latris.ai.context import build_context
    from latris.operations.project import update_selected_models

    root = tmp_path / "cld_with_loop"
    init_project(root, statement="Q?")
    update_selected_models(["cld"], root=root)
    a, _ = node_ops.add_node("A", kind="variable", root=root)
    b, _ = node_ops.add_node("B", kind="variable", root=root)
    edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    edge_ops.add_edge(b.id, a.id, kind="causal", root=root)

    pack = build_context("FindNewConnections", {}, ProjectPaths(root))
    assert "CLD loop-closure guidance" in pack.user
    assert "1 feedback loop(s) detected" in pack.user
    assert "NO feedback loops" not in pack.user


# ── Tier-0 evidence anchoring (AI interrogation Phase 2a) ────────────


def test_format_tier0_block_omits_refs_with_no_content() -> None:
    from latris.ai.context import _format_tier0_block
    from latris.schema import Reference

    refs = [
        Reference(bibkey="bare", title="Just a title"),
        Reference(bibkey="hasabs", title="Has abstract", abstract="Abstract text."),
    ]
    out = _format_tier0_block(refs)
    assert "bibkey=hasabs" in out
    assert "bibkey=bare" not in out


def test_format_tier0_block_truncates_at_limits() -> None:
    from latris.ai.context import _format_tier0_block
    from latris.schema import Reference

    long_abs = "A" * 1000
    long_notes = "B" * 1000
    refs = [Reference(bibkey="big", title="Big", abstract=long_abs, notes=long_notes)]
    out = _format_tier0_block(refs, abstract_chars=500, notes_chars=200)
    # 500 As, then nothing more before the closing quote on the abstract line.
    assert ("A" * 500) in out
    assert ("A" * 501) not in out
    assert ("B" * 200) in out
    assert ("B" * 201) not in out


def test_format_tier0_block_labels_landing_page_text() -> None:
    from latris.ai.context import _format_tier0_block
    from latris.schema import Reference, SourceSnapshot

    ref_landing = Reference(
        bibkey="landing",
        title="Landing-page snapshot only",
        source_snapshot=SourceSnapshot(
            retrieval_url="https://example.org/landing",
            content_hash="sha256:abc",
            extract="Generic publisher landing copy.",
            kind="landing_page_text",
        ),
    )
    ref_abs = Reference(
        bibkey="abs",
        title="Abstract snapshot",
        source_snapshot=SourceSnapshot(
            retrieval_url="https://example.org/abs",
            content_hash="sha256:def",
            extract="Real abstract content.",
            kind="abstract",
        ),
    )
    out = _format_tier0_block([ref_landing, ref_abs])
    assert "kind=landing_page_text" in out
    assert "NOT an abstract" in out
    assert "kind=abstract" in out


def test_build_suggest_citations_includes_tier0_block(tmp_path: Path, git_identity) -> None:
    """SuggestCitations context surfaces abstracts and a hard rule against
    treating user notes / landing-page text as abstract-grade."""
    from latris.ai.context import build_context
    from latris.operations import references as ref_ops

    root = tmp_path / "cite_proj"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("Pollution", kind="variable", root=root)

    ref_ops.add_reference("smith2024", title="Smith Study", root=root)
    ref_ops.update_reference("smith2024", notes="My note about this paper.", root=root)
    ref_ops.add_reference("doe2023", title="Doe Paper", root=root)
    # Mutate abstract via load/dump (no public CLI for setting abstract today).
    from latris.repo.yaml_io import dump_model, load_model
    from latris.schema import ReferenceLibrary

    lib_path = ProjectPaths(root).references_yaml
    lib = load_model(ReferenceLibrary, lib_path)
    next(r for r in lib.entries if r.bibkey == "doe2023").abstract = "Doe abstract content."
    dump_model(lib, lib_path)

    pack = build_context(
        "SuggestCitations",
        {"target_id": a.id, "target_attribute": "description"},
        ProjectPaths(root),
    )
    assert "Tier-0 source content" in pack.user
    assert "Doe abstract content." in pack.user
    assert "user-notes (NOT publisher source)" in pack.user
    assert "My note about this paper." in pack.user
    # Hard rule reminding the model that notes/landing-page do NOT
    # confer abstract-grade source access.
    assert "Tier-0 source content block above shows" in pack.user


def test_build_cross_reference_check_tier0_ranks_cited_first(tmp_path: Path, git_identity) -> None:
    from latris.ai.context import build_context
    from latris.operations import evidence as ev_ops
    from latris.operations import references as ref_ops

    root = tmp_path / "xref_proj"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("X", kind="variable", root=root)

    # 22 references — abstracts so they all show up in Tier-0 if budget allowed.
    for i in range(22):
        ref_ops.add_reference(f"r{i:02d}", title=f"Title {i}", root=root)
    from latris.repo.yaml_io import dump_model, load_model
    from latris.schema import ReferenceLibrary

    lib_path = ProjectPaths(root).references_yaml
    lib = load_model(ReferenceLibrary, lib_path)
    for r in lib.entries:
        r.abstract = f"Abstract for {r.bibkey}."
    dump_model(lib, lib_path)

    # Cite r21 only — verifies the cited bibkey wins ranking even though
    # its alphabetic position would not place it in the top-20.
    ev_ops.add_evidence(a.id, "description", "r21", root=root)

    pack = build_context("CrossReferenceCheck", {}, ProjectPaths(root))
    assert "Abstract for r21." in pack.user
    # Bottom-of-list r20 should make the top-20 cap; check that the cap
    # is applied (one of r00..r21 must be missing, since 22 > 20).
    missing = [bk for bk in (f"r{i:02d}" for i in range(22)) if f"Abstract for {bk}." not in pack.user]
    assert len(missing) == 2  # exactly two trimmed by the cap
    assert "r21" not in missing  # cited ref must NOT be trimmed


def test_build_context_suggest_edge_polarities_is_context_rich(populated_project) -> None:
    """SuggestEdgePolarities must see node kinds, the edge's existing polarity
    inline, and the edge's assumptions + evidence — so it can knowingly agree or
    disagree with an already-set value."""
    from latris.ai.context import build_context
    from latris.operations.evidence import add_evidence
    from latris.operations.provenance import add_assumption
    from latris.operations.references import add_reference
    from latris.repo.yaml_io import load_model

    sub = load_model(Substrate, populated_project.conceptual_yaml)
    edge = sub.edges[0]  # Price → Demand, polarity "-" already set by the fixture
    add_assumption("demand response is linear", target_id=edge.id, root=populated_project.root)
    add_reference("smith2020", "Smith", root=populated_project.root)
    add_evidence(edge.id, "existence", "smith2020", root=populated_project.root)

    pack = build_context(
        "SuggestEdgePolarities",
        {"model_type": "cld", "edges": [{"edge_id": edge.id, "from_label": "Price", "to_label": "Demand"}]},
        populated_project,
    )
    combined = pack.user
    assert "(variable)" in combined  # from/to node kinds
    assert "current polarity: -" in combined  # existing value shown inline
    assert "demand response is linear" in combined  # edge assumption
    assert "smith2020" in combined  # edge evidence


def test_foundation_summary_injects_scope_fields(populated_project) -> None:
    """Populated scope-contract fields (+ predictions) flow into the structural
    prompt's user message; the instruction to honour them is in the system."""
    from latris.ai.context import build_context
    from latris.operations.project import set_foundation_field

    fields = {
        "coverage_dimensions": "nutrient loading, sediment, riparian buffering",
        "granularity_level": "each node a measurable variable a manager tracks",
        "audience": "a regional catchment agency",
        "predictions": "quality declines under intensification then recovers with buffers",
    }
    for field, val in fields.items():
        set_foundation_field(field, val, root=populated_project.root)

    pack = build_context("DraftConceptualModel", {}, populated_project)
    for val in fields.values():
        assert val in pack.user, f"scope field value not injected into user message: {val!r}"
    assert "SCOPE CONTRACT" in pack.system


def test_foundation_summary_omits_unset_scope_fields(populated_project) -> None:
    """Unset scope fields add no noise — the labels don't appear when empty."""
    from latris.ai.context import build_context

    pack = build_context("DraftConceptualModel", {}, populated_project)
    assert "Coverage dimensions" not in pack.user
    assert "Audience:" not in pack.user
