"""Rendering AI results to text (``ai/render.py``).

The generic test walks every prompt in ``PROMPT_LIBRARY`` and renders a
fixture result of its response model twice: once with every field filled
(so each optional branch prints) and once with only the required fields (so
each "absent" branch runs). It fails on an exception, an empty rendering or a
``{placeholder}`` left unfilled. The targeted tests below pin the branches of
the renderers that print different text for empty and populated inputs.
"""

from __future__ import annotations

import enum
import re
import types
import typing
from typing import Any, Literal, Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from latris.ai import prompts as prompt_lib
from latris.ai import proposals as p
from latris.ai.proposals._shared import (
    CitationSuggestion,
    DraftAssumption,
    ExclusionEntry,
    QuestionEntry,
)
from latris.ai.proposals.interrogation import EdgeReclassifyAction
from latris.ai.proposals.model import DraftEdge, DraftEntity, DraftFraming, ProposedEdgeSketch
from latris.ai.proposals.references import SearchQuery, UncitedElement
from latris.ai.render import RENDERERS, render

_PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


# ── Fixture results, built from the response model's own fields ─────────


def _sample(tp: Any, full: bool) -> Any:
    origin = get_origin(tp)
    if origin is typing.Annotated:
        return _sample(get_args(tp)[0], full)
    if origin is Literal:
        return get_args(tp)[0]
    if origin in (Union, types.UnionType):
        return _sample(next(a for a in get_args(tp) if a is not type(None)), full)
    if origin in (list, tuple, set, frozenset):
        args = get_args(tp)
        return [_sample(args[0], full)] if args else []
    if origin is dict:
        key, value = get_args(tp) or (str, str)
        return {_sample(key, full): _sample(value, full)}
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return _build(tp, full)
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return next(iter(tp))
    if tp is dict:
        return {"key": "value"}
    if tp is bool:
        return True
    if tp is int:
        return 1
    if tp is float:
        return 0.5
    if tp in (str, Any):
        return "sample"
    raise TypeError(f"no fixture value for {tp!r}; extend _sample()")


def _build(cls: type[BaseModel], full: bool) -> BaseModel:
    """An instance of ``cls``: every field set when ``full``, else only the
    required ones (so optional fields fall back to their defaults)."""
    hints = typing.get_type_hints(cls)
    data = {
        name: _sample(hints.get(name, field.annotation), full)
        for name, field in cls.model_fields.items()
        if full or field.is_required()
    }
    return cls.model_validate(data)


@pytest.mark.parametrize("full", [True, False], ids=["all-fields", "required-only"])
@pytest.mark.parametrize("spec", prompt_lib.list_all(), ids=lambda s: s.name)
def test_every_prompt_result_renders(spec: prompt_lib.PromptSpec, full: bool) -> None:
    parsed = _build(spec.response_model, full)
    text = render(spec.name, parsed)
    assert isinstance(text, str), f"{spec.name}: render returned {type(text).__name__}"
    if full:
        assert text.strip(), f"{spec.name}: empty rendering of a populated result"
    leftover = _PLACEHOLDER.findall(text)
    assert not leftover, f"{spec.name}: unfilled placeholders {leftover} in:\n{text}"


def test_renderers_name_only_real_prompts() -> None:
    unknown = set(RENDERERS) - set(prompt_lib.PROMPT_LIBRARY)
    assert not unknown, f"renderers for prompts that don't exist: {sorted(unknown)}"


def test_unregistered_prompt_falls_back_to_json() -> None:
    parsed = p.ExplanationResult(explanation="why", referenced_ids=[])
    text = render("NoSuchPrompt", parsed)
    assert '"explanation": "why"' in text


# ── ExpandBibliography / FindFoundationalReferences ─────────────────────


def test_bibliography_plan_without_queries() -> None:
    assert render("ExpandBibliography", p.BibliographySearchPlan()) == "(no search queries proposed)"


def test_bibliography_plan_lists_queries_and_rationale() -> None:
    plan = p.BibliographySearchPlan(
        queries=[
            SearchQuery(query="price elasticity", rationale="core link"),
            SearchQuery(query="demand shocks"),
        ]
    )
    text = render("FindFoundationalReferences", plan)
    assert text.splitlines() == [
        "Search queries:",
        "  [1] price elasticity",
        "      core link",
        "  [2] demand shocks",
    ]


def test_bibliography_results_empty() -> None:
    assert render("ExpandBibliography", p.ExpandBibliographyProposal()) == "(no new references proposed)"


def test_bibliography_results_cap_authors_and_skip_absent_fields() -> None:
    proposal = p.ExpandBibliographyProposal(
        new_references=[
            CitationSuggestion(
                bibkey="a2020",
                title="Full",
                authors=["A", "B", "C", "D"],
                year=2020,
                doi="10.1/x",
            ),
            CitationSuggestion(bibkey="b", title="Bare"),
        ]
    )
    lines = render("ExpandBibliography", proposal).splitlines()
    assert lines[0] == "Proposed references:"
    assert lines[1] == "  [a2020] Full | A, B, C | 2020 | DOI:10.1/x"
    assert lines[2] == "  [b] Bare"


# ── CrossReferenceCheck ─────────────────────────────────────────────────


def test_cross_reference_all_clear() -> None:
    text = render("CrossReferenceCheck", p.CrossReferenceCheckResult())
    assert text == "\nAll elements have evidence; all references are cited."


def test_cross_reference_lists_gaps() -> None:
    result = p.CrossReferenceCheckResult(
        coverage_summary="2 of 3 cited.",
        uncited_elements=[
            UncitedElement(element_id="ent_0123456789abcdefXYZ", attributes_without_evidence=[]),
            UncitedElement(element_id="ent_2", label="Demand", attributes_without_evidence=["polarity", "delay"]),
        ],
        unused_references=["smith2024"],
    )
    text = render("CrossReferenceCheck", result)
    assert text.startswith("2 of 3 cited.")
    assert "Uncited elements (2):" in text
    # No label: the id is shortened; no attributes: "general".
    assert "  - ent_0123456789ab (missing: general)" in text
    assert "  - Demand (missing: polarity, delay)" in text
    assert "Unused references (1):\n  - smith2024" in text
    assert "All elements have evidence" not in text


def test_cross_reference_only_unused_references() -> None:
    text = render("CrossReferenceCheck", p.CrossReferenceCheckResult(unused_references=["k"]))
    assert "Uncited elements" not in text
    assert "Unused references (1):" in text
    assert "All elements have evidence" not in text


# ── FindCounterPathway ──────────────────────────────────────────────────


def test_counter_pathway_minimal() -> None:
    result = p.CounterPathwayResult(missing_mechanism="Substitution", argument="Buyers switch.", record_question=False)
    assert render("FindCounterPathway", result) == "Missing mechanism: Substitution\n\nArgument: Buyers switch."


def test_counter_pathway_full() -> None:
    result = p.CounterPathwayResult(
        missing_mechanism="Substitution",
        argument="Buyers switch.",
        supporting_bibkey="lee2021",
        proposed_nodes=["Substitutes"],
        proposed_edges=[
            ProposedEdgeSketch(from_label="Price", to_label="Substitutes", polarity="+", rationale="switching"),
            ProposedEdgeSketch(from_label="Substitutes", to_label="Demand", polarity="-"),
        ],
        record_question=True,
    )
    text = render("FindCounterPathway", result)
    assert "Supporting reference: lee2021" in text
    assert "Proposed new nodes (advisory):\n  - Substitutes" in text
    assert "  - Price →(+) Substitutes — switching" in text
    assert text.splitlines().count("  - Substitutes →(-) Demand") == 1
    assert "  - log open question: counter-pathway 'Substitution'" in text


def test_counter_pathway_blank_mechanism_records_nothing() -> None:
    result = p.CounterPathwayResult(missing_mechanism="  ", argument="x", record_question=True)
    assert "Proposed records" not in render("FindCounterPathway", result)


# ── ScopeCheck ──────────────────────────────────────────────────────────


def test_scope_check_verdict_only() -> None:
    assert render("ScopeCheck", p.ScopeCheckResult(verdict="in scope")) == "Verdict: in scope"


def test_scope_check_full() -> None:
    result = p.ScopeCheckResult(
        verdict="too broad",
        reasoning="Covers two markets.",
        suggestions=["Narrow to one market"],
        proposed_exclusions=[ExclusionEntry(statement="Exports", rationale="out of boundary")],
        proposed_questions=[QuestionEntry(question="Which market?")],
    )
    text = render("ScopeCheck", result)
    assert "Reasoning: Covers two markets." in text
    assert "Suggestions:\n  - Narrow to one market" in text
    assert "Proposed exclusions:\n  - Exports (out of boundary)" in text
    assert "Proposed questions:\n  - Which market?" in text


# ── DraftConceptualModel ────────────────────────────────────────────────


def test_draft_with_no_framings_is_empty() -> None:
    assert render("DraftConceptualModel", p.DraftModelProposal()) == ""


def test_draft_bare_framing() -> None:
    proposal = p.DraftModelProposal(
        framings=[
            DraftFraming(
                name="Minimal",
                entities=[DraftEntity(label="Price", kind="variable")],
                edges=[DraftEdge(from_label="Price", to_label="Demand", kind="causal")],
            )
        ]
    )
    text = render("DraftConceptualModel", proposal)
    assert "--- Framing 0: Minimal ---" in text
    assert "Rationale" not in text
    assert "    - Price (variable)" in text
    assert "    - Price -> Demand (causal)" in text
    assert "[" not in text.split("Edges:")[1]  # no polarity tag
    assert "Assumptions" not in text


def test_draft_full_framing() -> None:
    proposal = p.DraftModelProposal(
        framings=[
            DraftFraming(
                name="Rich",
                rationale="Captures feedback.",
                entities=[DraftEntity(label="Price", kind="variable", description="Unit price")],
                edges=[
                    DraftEdge(
                        from_label="Price", to_label="Demand", kind="causal", polarity="-", description="law of demand"
                    )
                ],
                assumptions=[
                    DraftAssumption(statement="Elastic market", rationale="observed", target_label="Demand"),
                    DraftAssumption(statement="No rationing"),
                ],
            ),
            DraftFraming(name="Second"),
        ]
    )
    text = render("DraftConceptualModel", proposal)
    assert "  Rationale: Captures feedback." in text
    assert "      Unit price" in text
    assert "    - Price -> Demand (causal) [-]" in text
    assert "      law of demand" in text
    assert "    - Elastic market (re: Demand)" in text
    assert "      observed" in text
    assert "    - No rationing" in text
    assert "--- Framing 1: Second ---" in text


# ── Interrogation lambdas (branch on the action/verdict) ────────────────


def test_verify_claim_quote_only_when_supported() -> None:
    supports = p.VerifyClaimAgainstSourceProposal(
        attribute="polarity", bibkey="k", claim="c", verdict="supports", quote="exact words", confidence="high"
    )
    refutes = supports.model_copy(update={"verdict": "contradicts"})
    assert 'quote: "exact words"' in render("VerifyClaimAgainstSource", supports)
    assert "quote" not in render("VerifyClaimAgainstSource", refutes)


@pytest.mark.parametrize(
    ("action", "extra", "expected"),
    [
        ("evidence_search", {"search_query": "elasticity"}, "→ query: 'elasticity'"),
        ("polarity_flip", {"new_polarity": "+"}, "→ polarity: +"),
        ("keep", {}, "action: keep"),
    ],
)
def test_challenge_edge_actions(action: str, extra: dict[str, str], expected: str) -> None:
    parsed = p.ChallengeEdgeProposal(target_id="edg_1", action=action, confidence="low", **extra)
    text = render("ChallengeEdge", parsed)
    assert expected in text
    assert "→" not in text or action != "keep"


def test_evidence_demote_new_verdict_only_on_change() -> None:
    change = p.EvidenceDemoteProposal(attribute="a", bibkey="k", action="change_verdict", new_verdict="weak")
    keep = change.model_copy(update={"action": "keep"})
    assert "→ verdict: weak" in render("EvidenceDemote", change)
    assert "verdict" not in render("EvidenceDemote", keep)


def test_edge_reclassify_each_action() -> None:
    parsed = p.EdgeReclassifyProposal(
        summary="Three edges reviewed.",
        actions=[
            EdgeReclassifyAction(target_id="e1", action="keep", confidence="high"),
            EdgeReclassifyAction(target_id="e2", action="retag", new_kind="correlational", rationale="no mechanism"),
            EdgeReclassifyAction(target_id="e3", action="remove", rationale="duplicate"),
        ],
    )
    lines = render("EdgeReclassify", parsed).splitlines()
    assert lines[0] == "Three edges reviewed."
    assert lines[2].endswith("e1: keep")
    assert lines[3].endswith("e2: retag → correlational — no mechanism")
    assert lines[4].endswith("e3: remove — duplicate")


def test_elicitation_shows_proposed_edit_only_when_present() -> None:
    with_edit = p.ElicitationTurnResult(question="Why?", proposed_edit={"op": "add"})
    assert render("RunElicitationInterview", with_edit).startswith("Question: Why?\nProposed edit:")
    assert render("RunElicitationInterview", p.ElicitationTurnResult(question="Why?")) == "Question: Why?"
