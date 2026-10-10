"""Phase 6b: hermetic context-builder smoke tests.

Every prompt registered in `PROMPT_LIBRARY` must build a non-empty
`ContextPack` against a small populated fixture project. This catches
silent schema drift in `ai/context.py` builders the moment a substrate
or attribute field is renamed — long before the broken prompt ships
to a user.

The tests do NOT invoke the model: `build_context` is pure dispatch
(no adapter call), so the assertion surface is "the builder ran
without raising and produced a system + user pack". That keeps the
suite fast and decoupled from mock-response drift.

Companion to Phase 6a (capability_example coverage sweep), which
exercises the same prompts end-to-end against real AI to catch
*quality* drift. Together they close the validation-coverage bullet
in `docs/design/AI_INTERROGATION.md`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latris.ai import prompts as prompt_lib
from latris.ai.context import _BUILDERS, build_context
from latris.operations import attributes as attr_ops
from latris.operations import edges as edge_ops
from latris.operations import evidence as ev_ops
from latris.operations import nodes as node_ops
from latris.operations import provenance as prov_ops
from latris.operations import references as ref_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.operations.interpret import initialise_sections, refresh_all_claims
from latris.operations.project import update_selected_models
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from tests.conftest import build_with_template_identity, clone_project

# ── Skip set ─────────────────────────────────────────────────────────
#
# Map prompt name → reason for skipping the smoke test. Skips are
# *documented* and *auditable* — the coverage-assertion test at the
# bottom of this module fails if a new prompt lands without either a
# synthesised input set or a recorded skip rationale.

_SKIP_REASONS: dict[str, str] = {
    # Multi-turn workflow: a one-shot batch invocation does not exercise
    # the prior_turns/answers state machine, so the smoke test would be
    # a meaningless tautology.
    "RunElicitationInterview": (
        "multi-turn workflow; smoke test cannot exercise loop semantics"
    ),
}


# ── Kitchen-sink fixture ─────────────────────────────────────────────


_FIXTURE_BIBKEY = "smoke2024"


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the mock adapter at import-time so any incidental adapter
    lookups during context building hit the no-op stub.

    `build_context` itself does not invoke the adapter (verified at
    `context.py:2453-2462`), but a few builders import `call`-side
    helpers and we keep the env-var consistent with the rest of the AI
    test suite.
    """
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")


@pytest.fixture(scope="module")
def _kitchen_sink_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Project populated with one of every substrate element a builder
    might dereference.

    The intent is that *no* builder skips a code path because the
    relevant collection is empty. If a builder reads entities, it sees
    two; if it reads references, it sees one with a snapshot; if it
    reads evidence links, it sees one; if it reads assumptions /
    questions / interpret sections, those exist too.
    """

    def build() -> Path:
        root = tmp_path_factory.mktemp("smoke_tpl") / "proj"
        init_project(root, statement="What drives demand?")
        update_selected_models(["cld"], root=root)

        # Two variables; one carries a description attribute so the
        # SuggestCitations / FillProvenanceField paths see populated
        # per-attribute state.
        price, _ = node_ops.add_node("Price", kind="variable", root=root)
        demand, _ = node_ops.add_node("Demand", kind="variable", root=root)
        attr_ops.set_attribute(price.id, "description", "Market price level", root=root)

        # One causal edge with CLD polarity so the view-attribute
        # readers (EdgeReclassify, ChallengeEdge, SuggestEdgePolarities)
        # find polarity data and not just bare edge kind.
        edge, _ = edge_ops.add_edge(price.id, demand.id, kind="causal", root=root)
        view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)

        # One reference with a source snapshot so
        # VerifyClaimAgainstSource's apply-time validator has an
        # extract to point at (verification itself is not invoked here
        # — we are only building context).
        ref_ops.add_reference(
            _FIXTURE_BIBKEY,
            title="Demand dynamics under price shocks",
            authors=["Smith, J."],
            year=2024,
            root=root,
        )
        ref_ops.set_source_snapshot(
            _FIXTURE_BIBKEY,
            retrieval_url="https://example.com/smoke",
            extract=(
                "Price increases reduce demand in elastic markets. "
                "The effect is strongest for non-essential goods."
            ),
            kind="abstract",
            root=root,
        )

        # Evidence link on the edge's polarity attribute so the
        # EvidenceDemote / VerifyClaimAgainstSource builders find a
        # matching (target_id, attribute, bibkey) tuple in the store.
        ev_ops.add_evidence(
            edge.id, "polarity", _FIXTURE_BIBKEY, verified_by="human", root=root
        )

        # Provenance rows so builders that surface assumptions /
        # questions in their context blocks don't render empty sections.
        prov_ops.add_assumption(
            "Price elasticity is positive.",
            rationale="Required for demand response to be observable.",
            target_id=price.id,
            root=root,
        )
        prov_ops.add_question(
            "Is Price observable in real time?",
            target_id=price.id,
            root=root,
        )

        # Interpret state initialised + claims refreshed so the shared
        # `_build_interpret_section` builder has section + claim data
        # to read for every section_type. `initialise_sections` skips
        # any model type that fails readiness (a CLD with no loops
        # fails the loops gate); the smoke test still exercises the
        # context builder on the empty-section path, which is itself
        # the regression we care about — a future schema change must
        # not crash that branch.
        initialise_sections(root=root)
        refresh_all_claims(root=root)

        return root

    return build_with_template_identity(build)


@pytest.fixture
def smoke_project(
    _kitchen_sink_template: Path,
    tmp_path: Path,
    git_identity,
) -> ProjectPaths:
    cloned = clone_project(_kitchen_sink_template, tmp_path / "proj")
    return ProjectPaths(cloned)


@pytest.fixture(scope="module")
def _fixture_ids(_kitchen_sink_template: Path) -> dict[str, str]:
    """Resolve template IDs by label once per module.

    `clone_project` is a `shutil.copytree`, so cloned projects share
    the template's IDs. Reading once at module scope keeps the
    parametrized cases fast.
    """
    substrate = load_model(Substrate, ProjectPaths(_kitchen_sink_template).conceptual_yaml)
    price = next(e for e in substrate.entities if e.label == "Price")
    demand = next(e for e in substrate.entities if e.label == "Demand")
    edge = substrate.edges[0]
    return {
        "node_id": price.id,
        "other_node_id": demand.id,
        "edge_id": edge.id,
        "bibkey": _FIXTURE_BIBKEY,
    }


# ── Input synthesis ──────────────────────────────────────────────────


# Prompt name → InterpretSection section_type id. The 10 Interpret*
# prompts share one context builder and disambiguate by section_type.
_INTERPRET_SECTION_TYPES = {
    "InterpretStructuralSummary": "structural_summary",
    "InterpretKeyFindings": "key_findings",
    "InterpretSensitivity": "sensitivity",
    "InterpretAssumptions": "assumptions",
    "InterpretEvidenceGaps": "evidence_gaps",
    "InterpretEvidenceCoverage": "evidence_coverage",
    "InterpretAnswer": "answer",
    "InterpretImplications": "implications",
    "InterpretConfidence": "confidence",
    "InterpretOpenQuestions": "open_questions",
}


def _synthesise_inputs(prompt_name: str, ids: dict[str, str]) -> dict[str, Any]:
    """Return the minimal valid input dict for a prompt.

    Hand-written dispatch (rather than reflection) because input fields
    are heterogeneous — some accept any element, some require an edge
    specifically, some take a bibkey, a view name, etc. Keeping the
    mapping explicit makes it obvious which fixture value each prompt
    consumes.
    """
    if prompt_name in _INTERPRET_SECTION_TYPES:
        return {
            "section_type": _INTERPRET_SECTION_TYPES[prompt_name],
            "model_type": "cld",
            "claims": ["Sample claim for smoke-test context."],
        }

    node_id = ids["node_id"]
    edge_id = ids["edge_id"]
    bibkey = ids["bibkey"]

    table: dict[str, dict[str, Any]] = {
        # Model-scope, no required inputs (defaults cover everything).
        "AttackThisModel": {},
        "FindCounterPathway": {},
        "CrossReferenceCheck": {},
        "IdentifyResearchGaps": {},
        "ScopeCheck": {},
        "ScanEvidenceGaps": {},
        "SuggestExclusions": {},
        "FindNewConnections": {},
        "SuggestEdgePolarities": {},
        "RecommendApproach": {},
        "SuggestVariables": {},
        "SuggestConnections": {},
        "ExtractVariablesFromEvidence": {},
        "ExtractCausalClaims": {},
        "ExpandBibliography": {},
        "FindFoundationalReferences": {},
        "EdgeReclassify": {"model_type": "cld"},
        "CompletenessGate": {"model_type": "cld"},
        "StoryBeatProse": {"beat_kind": "answer", "source_text": "Sample grounded content.", "model_type": "cld"},
        # Model-scope with required fields.
        "DraftConceptualModel": {"focus": "smoke-test focus"},
        "ProjectToFormalView": {"view": "cld"},
        "GeneratePack": {"pack": "client"},
        "SyntheticPeerReview": {},  # reviewer_role has a default
        # Element-scope (node target).
        "ExplainThisElement": {"target_id": node_id},
        "GenerateAssumptions": {"target_id": node_id},
        "RaiseQuestions": {"target_id": node_id},
        "SuggestDecisions": {"target_id": node_id},
        "SteelmanOpposingView": {"target_id": node_id},
        "SuggestCitations": {"target_id": node_id, "target_attribute": "description"},
        # Element-scope (edge target).
        "ChallengeThisConnection": {"target_id": edge_id, "target_attribute": "polarity"},
        "ChallengeEdge": {"edge_id": edge_id, "model_type": "cld"},
        # Element-scope (evidence-link target — addressed by tuple).
        "EvidenceDemote": {
            "target_id": edge_id,
            "attribute": "polarity",
            "bibkey": bibkey,
        },
        "VerifyClaimAgainstSource": {
            "target_id": edge_id,
            "attribute": "polarity",
            "bibkey": bibkey,
            "claim": "Price increases reduce demand in elastic markets.",
        },
        # Element-scope (reference target).
        "SummarizeReference": {"bibkey": bibkey},
        # Inline per-field AI.
        "FillProvenanceField": {
            "target_kind": "entity",
            "target_id": node_id,
            "field_path": "notes",
            "current_value": "",
        },
    }
    if prompt_name not in table:
        raise KeyError(
            f"smoke test has no input recipe for {prompt_name!r}; add an "
            "entry to _synthesise_inputs() or _SKIP_REASONS."
        )
    return table[prompt_name]


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "spec",
    prompt_lib.list_all(),
    ids=lambda s: s.name,
)
def test_build_context_smoke(
    spec: prompt_lib.PromptSpec,
    smoke_project: ProjectPaths,
    _fixture_ids: dict[str, str],
) -> None:
    """Every prompt's context builder runs without raising on the
    kitchen-sink fixture and returns a non-empty pack."""
    if spec.name in _SKIP_REASONS:
        pytest.skip(_SKIP_REASONS[spec.name])

    inputs = _synthesise_inputs(spec.name, _fixture_ids)

    # Round-trip the inputs through the declared schema to mirror what
    # the CLI dispatch does — catches input-schema drift on top of
    # builder drift.
    spec.inputs.model_validate(inputs)

    pack = build_context(spec.name, inputs, smoke_project)

    assert pack.system, f"{spec.name}: empty system message"
    assert pack.user, f"{spec.name}: empty user message"
    assert isinstance(pack.target_ids, list), f"{spec.name}: target_ids must be a list"


def test_every_builder_is_covered() -> None:
    """Every dispatcher entry has either a smoke input recipe or a
    documented skip. Guards against a future prompt landing in
    `_BUILDERS` without smoke coverage."""
    builder_names = set(_BUILDERS.keys())
    library_names = set(prompt_lib.PROMPT_LIBRARY.keys())

    # _BUILDERS keys must all be valid prompt names (cross-check the
    # other direction).
    unknown_builders = builder_names - library_names
    assert not unknown_builders, (
        f"_BUILDERS has entries with no matching PROMPT_LIBRARY spec: "
        f"{sorted(unknown_builders)}"
    )

    missing_specs = library_names - builder_names
    assert not missing_specs, (
        f"PROMPT_LIBRARY has prompts with no _BUILDERS entry: "
        f"{sorted(missing_specs)}"
    )

    # Every prompt name must be in either the synthesis table or the
    # skip set. We discover synthesis-table coverage by calling the
    # helper with placeholder IDs and checking for KeyError.
    placeholder_ids = {
        "node_id": "x",
        "other_node_id": "y",
        "edge_id": "z",
        "bibkey": "k",
    }
    uncovered: list[str] = []
    for name in sorted(library_names):
        if name in _SKIP_REASONS:
            continue
        try:
            _synthesise_inputs(name, placeholder_ids)
        except KeyError:
            uncovered.append(name)

    assert not uncovered, (
        f"Prompts missing smoke coverage: {uncovered}. "
        "Add an entry to _synthesise_inputs() or _SKIP_REASONS with a rationale."
    )


# ── Guidance-reaches-the-model regression lock ───────────────────────
#
# Root cause of the node-inconsistency bug: the granularity guidance lives on
# `PromptSpec.template`, but the node-producing builders used to hand-write
# their own task text and never send the template — so the guidance was dead
# code. Pass 1 routes each spec's template into the system prompt via
# `compose_system`. These tests lock that in: the guidance must appear in the
# assembled prompt for node/edge-producing operations.

# Node-producing prompts whose templates carry the mechanistic-granularity
# guidance + kind rubric (prompts.py).
_GRANULARITY_PROMPTS = [
    "DraftConceptualModel",
    "ExtractVariablesFromEvidence",
    "SuggestVariables",
]

# A distinctive substring of _MECHANISTIC_GRANULARITY_GUIDANCE that must survive
# into the sent prompt now the template is routed into the system message.
_GRANULARITY_MARKER = "MECHANISTIC GRANULARITY"


@pytest.mark.parametrize("prompt_name", _GRANULARITY_PROMPTS)
def test_granularity_guidance_reaches_the_model(
    prompt_name: str,
    smoke_project: ProjectPaths,
    _fixture_ids: dict[str, str],
) -> None:
    """The mechanistic-granularity guidance AND the node-kind rubric must appear
    in the assembled prompt for node-producing operations — the regression lock
    for the inconsistency bug."""
    inputs = _synthesise_inputs(prompt_name, _fixture_ids)
    pack = build_context(prompt_name, inputs, smoke_project)
    combined = f"{pack.system}\n{pack.user}"
    assert _GRANULARITY_MARKER in combined, (
        f"{prompt_name}: granularity guidance ({_GRANULARITY_MARKER!r}) is not "
        "present in the assembled prompt — the guidance is not being sent."
    )
    assert "NODE KIND" in combined, (
        f"{prompt_name}: node-kind rubric is not present in the assembled prompt."
    )


# The mutating structural authors must also carry the provenance + polarity
# guidance into the sent prompt, so assumptions / source_bibkeys / polarity are
# authored in the same call as the edit (Workstream A/B of the provenance plan).
_STRUCTURAL_AUTHOR_PROMPTS = ["DraftConceptualModel", "FindNewConnections"]


@pytest.mark.parametrize("prompt_name", _STRUCTURAL_AUTHOR_PROMPTS)
def test_provenance_and_polarity_guidance_reaches_the_model(
    prompt_name: str,
    smoke_project: ProjectPaths,
    _fixture_ids: dict[str, str],
) -> None:
    """The entity-provenance rubric (source_bibkeys / rubric-gated assumptions)
    and the edge-polarity co-authoring rule must appear in the assembled prompt
    for the mutating structural authors."""
    inputs = _synthesise_inputs(prompt_name, _fixture_ids)
    pack = build_context(prompt_name, inputs, smoke_project)
    combined = f"{pack.system}\n{pack.user}"
    assert "source_bibkeys" in combined, (
        f"{prompt_name}: entity-provenance guidance is not in the assembled prompt."
    )
    assert "polarity_rationale" in combined, (
        f"{prompt_name}: edge-polarity co-authoring guidance is not in the assembled prompt."
    )


# Every structural author must carry the scope-contract instruction so a
# populated coverage-dimensions / granularity / audience is honoured.
_SCOPE_STRUCTURAL_PROMPTS = [
    "DraftConceptualModel",
    "FindNewConnections",
    "ExtractVariablesFromEvidence",
    "SuggestVariables",
    "ExtractCausalClaims",
    "SuggestConnections",
]


@pytest.mark.parametrize("prompt_name", _SCOPE_STRUCTURAL_PROMPTS)
def test_scope_contract_guidance_reaches_the_model(
    prompt_name: str,
    smoke_project: ProjectPaths,
    _fixture_ids: dict[str, str],
) -> None:
    """The scope-contract instruction must reach the system prompt of every
    structural author so declared coverage dimensions / granularity / audience
    are honoured."""
    inputs = _synthesise_inputs(prompt_name, _fixture_ids)
    pack = build_context(prompt_name, inputs, smoke_project)
    assert "SCOPE CONTRACT" in pack.system, (
        f"{prompt_name}: scope-contract guidance is not in the assembled system prompt."
    )


def test_steer_input_is_injected_into_user_message(
    smoke_project: ProjectPaths,
    _fixture_ids: dict[str, str],
) -> None:
    """An optional `steer` input is appended uniformly as a <user_guidance>
    block by build_context, for any prompt, without a per-builder change."""
    steer = "Prioritise nutrient-loading variables at a mechanistic level."
    inputs = {**_synthesise_inputs("SuggestVariables", _fixture_ids), "steer": steer}
    pack = build_context("SuggestVariables", inputs, smoke_project)
    assert "<user_guidance>" in pack.user
    assert steer in pack.user

    # Absent/blank steer must not add the block.
    plain = build_context("SuggestVariables", _synthesise_inputs("SuggestVariables", _fixture_ids), smoke_project)
    assert "<user_guidance>" not in plain.user
