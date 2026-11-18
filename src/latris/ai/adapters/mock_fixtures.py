"""Placeholder AI responses for working on the app with ``LATRIS_AI_MOCK=1``.

Registered as the mock adapter's defaults, one per response type, so every
AI button returns something plausible without a model. Tests register their
own responses and don't use these.
"""

from __future__ import annotations


def register_gui_defaults() -> None:
    """Pre-register placeholder mock AI responses for GUI development.

    The server calls this at startup when ``LATRIS_AI_MOCK=1``. Without this,
    every AI button in the GUI would fail with a ``LookupError`` because no
    canned responses are registered.
    """
    from latris.ai import proposals as p
    from latris.ai.adapters.base import ChatResult
    from latris.ai.adapters.mock_adapter import MockAdapter

    mock = MockAdapter.shared()

    mock.register_default(
        response_cls=p.ExplanationResult,
        result=ChatResult(
            parsed=p.ExplanationResult(
                explanation="(mock) This element exists because it is a key driver in the current causal framing.",
                referenced_ids=[],
            ),
            raw="(mock)",
            model_id="mock-model",
            token_usage={"input_tokens": 50, "output_tokens": 30},
            cost_usd=0.001,
        ),
    )
    mock.register_default(
        response_cls=p.ApproachRecommendationResult,
        result=ChatResult(
            parsed=p.ApproachRecommendationResult(
                recommendations=[
                    p.ApproachRecommendation(
                        model_type_id="cld",
                        suitability="recommended",
                        rationale="(mock) The question centres on feedback dynamics, which a CLD captures.",
                    ),
                    p.ApproachRecommendation(
                        model_type_id="dag",
                        suitability="consider",
                        rationale="(mock) A DAG sharpens causal claims when you need adjustment sets.",
                    ),
                ],
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.ChallengeProposal,
        result=ChatResult(
            parsed=p.ChallengeProposal(
                target_id="PLACEHOLDER",
                argument="(mock) The assumed relationship may be confounded by unmodelled factors.",
                opening_turn="Consider alternative mechanisms.",
                recommended_state="retained-with-caveat",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.CitationsProposal,
        result=ChatResult(
            parsed=p.CitationsProposal(new_references=[], evidence_links=[]),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.DraftModelProposal,
        result=ChatResult(
            parsed=p.DraftModelProposal(
                framings=[
                    p.DraftFraming(
                        name="Default framing",
                        entities=[
                            p.DraftEntity(label="Factor A", kind="concept", description="(mock) A placeholder factor.")
                        ],
                        edges=[],
                        assumptions=[],
                        rationale="(mock) Single-factor placeholder.",
                    )
                ]
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.AttackResult,
        result=ChatResult(
            parsed=p.AttackResult(
                weakest_assumption="(mock) Linear relationship assumed",
                argument="(mock) Non-linear effects are well-documented in the literature.",
                affected_node_ids=[],
                recommended_action="Add a non-linearity caveat.",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.ScopeCheckResult,
        result=ChatResult(
            parsed=p.ScopeCheckResult(
                verdict="well-matched",
                suggestions=[],
                reasoning="(mock) The model adequately covers the foundation question.",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.NewConnectionsProposal,
        result=ChatResult(
            parsed=p.NewConnectionsProposal(proposals=[]),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.ElicitationTurnResult,
        result=ChatResult(
            parsed=p.ElicitationTurnResult(
                question="(mock) What is the primary mechanism you would expect?", proposed_edit=None
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.ReportDraft,
        result=ChatResult(
            parsed=p.ReportDraft(
                pack="client",
                sections=[
                    p.ReportSection(
                        heading="Summary",
                        content="(mock) Placeholder report content.",
                    ),
                ],
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.PeerReviewResult,
        result=ChatResult(
            parsed=p.PeerReviewResult(
                reviewer_role="domain expert",
                scope_assessment="(mock) Scope is adequate.",
                rigor_assessment="(mock) Causal claims are plausible.",
                evidence_assessment="(mock) Evidence base is thin.",
                major_risks=["(mock) Single-source dependency"],
                proposed_questions=["(mock) What confounders have been considered?"],
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.ResearchGapsResult,
        result=ChatResult(
            parsed=p.ResearchGapsResult(
                gaps=[
                    p.ResearchGap(
                        description="(mock) Key mechanism lacks empirical support.",
                        priority="high",
                        affected_node_ids=[],
                        suggested_action="Attach supporting reference.",
                    )
                ]
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.SteelmanProposal,
        result=ChatResult(
            parsed=p.SteelmanProposal(
                target_id="PLACEHOLDER",
                opposing_view="(mock) The opposing position is that this factor is secondary, not primary.",
                rationale="(mock) Alternative studies suggest a weaker effect.",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.FormalViewProjectionResult,
        result=ChatResult(
            parsed=p.FormalViewProjectionResult(
                target_view="cld",
                recommended_mappings=[],
                conflicts=["(mock) Some edges lack polarity for CLD."],
                rationale="(mock) Substrate maps well but needs polarity.",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.CrossReferenceCheckResult,
        result=ChatResult(
            parsed=p.CrossReferenceCheckResult(
                uncited_elements=[],
                unused_references=[],
                coverage_summary="(mock) Coverage is adequate for the current model maturity.",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.BibliographySearchPlan,
        result=ChatResult(
            parsed=p.BibliographySearchPlan(
                queries=[
                    p.SearchQuery(
                        query="(mock) water quality estuary monitoring", rationale="(mock) Core research topic"
                    )
                ]
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.ReferenceRelevanceResult,
        result=ChatResult(
            parsed=p.ReferenceRelevanceResult(
                bibkey="(mock)",
                relevance_summary="(mock) This reference provides foundational evidence.",
                connected_elements=[],
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.AssumptionsProposal,
        result=ChatResult(
            parsed=p.AssumptionsProposal(
                target_id="PLACEHOLDER",
                assumptions=[
                    p.DraftAssumption(
                        statement="(mock) Linear relationship assumed between variables.",
                        rationale="(mock) Simplification appropriate at current maturity.",
                    )
                ],
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.DecisionsProposal,
        result=ChatResult(
            parsed=p.DecisionsProposal(
                target_id="PLACEHOLDER",
                decisions=[
                    p.DecisionEntry(
                        statement="(mock) Chose variable representation over concept.",
                        rationale="(mock) Enables future quantification.",
                    )
                ],
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.ExclusionsProposal,
        result=ChatResult(
            parsed=p.ExclusionsProposal(
                exclusions=[
                    p.ExclusionEntry(
                        statement="(mock) Temporal dynamics excluded.",
                        rationale="(mock) Steady-state assumption at this stage.",
                    )
                ]
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.QuestionsProposal,
        result=ChatResult(
            parsed=p.QuestionsProposal(
                target_id="PLACEHOLDER",
                questions=[p.QuestionEntry(question="(mock) What is the dose-response relationship?")],
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.AttributeSuggestionsResult,
        result=ChatResult(
            parsed=p.AttributeSuggestionsResult(suggestions=[]),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.FillFieldProposal,
        result=ChatResult(
            parsed=p.FillFieldProposal(
                value="(mock) suggested value",
                rationale="(mock) Plausible default given the project context.",
                confidence="medium",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.EvidenceGapsScanResult,
        result=ChatResult(
            parsed=p.EvidenceGapsScanResult(
                gaps=[
                    p.EvidenceGap(
                        section_type="key_findings",
                        claim="(mock) primary causal claim",
                        gap_description="(mock) lacks empirical support",
                        suggested_action="(mock) attach a supporting reference",
                        severity="medium",
                    )
                ],
                summary="(mock) Evidence base is uneven across sections.",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
    mock.register_default(
        response_cls=p.InterpretProseResult,
        result=ChatResult(
            parsed=p.InterpretProseResult(
                prose="(mock) In plain terms, the model shows how the main drivers connect.",
            ),
            raw="(mock)",
            model_id="mock-model",
        ),
    )
