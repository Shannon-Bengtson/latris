"""FastAPI application factory.

The server wraps ``latris.operations`` over HTTP so the React GUI
can talk to the same business logic the CLI uses.  The Python backend is
always the source of truth; React state is a disposable read cache.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import latris
from latris.ai.adapters import mock_enabled
from latris.operations._resolve import ResolveError
from latris.repo.git import IdentityError
from latris.repo.layout import ProjectPaths
from latris.repo.project import NotAProjectError
from latris.repo.yaml_io import load_model
from latris.schema import (
    ProjectFoundation,
    Substrate,
)
from latris.server.deps import get_project_root
from latris.server.perf import PerfMiddleware
from latris.server.routes import (
    activity,
    ai,
    analysis,
    annotations,
    attributes,
    bn,
    challenges,
    checks,
    completeness,
    compose,
    configure,
    datasets,
    edges,
    evidence,
    export,
    fcm,
    findings,
    history,
    interpret,
    layout,
    lineage,
    model_choices,
    model_types,
    nodes,
    provenance,
    readiness,
    references,
    report_config,
    review,
    story,
    sync,
    view_attributes,
    views,
)
from latris.server.routes import (
    help as help_routes,
)
from latris.server.state import load_full_state
from latris.server.watch import manager, watch_project

Root = Annotated[Path, Depends(get_project_root)]


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    statement: str | None = None
    background: str | None = None
    boundary: str | None = None
    exclusions: str | None = None
    predictions: str | None = None
    coverage_dimensions: str | None = None
    granularity_level: str | None = None
    audience: str | None = None
    selected_model_types: list[str] | None = None


def _register_server_mock_responses() -> None:
    """Pre-register placeholder mock AI responses for GUI development.

    Called at server startup when ``LATRIS_AI_MOCK=1``. Without this,
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


def create_app(*, project_root: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    project_root:
        Explicit project directory. Falls back to the ``LATRIS_PROJECT_ROOT``
        env var, then ``find_project_root()`` from the server's cwd.
    """
    # Allow env-var override (used by dev-server.sh with uvicorn --factory --reload).
    if project_root is None:
        env_root = os.environ.get("LATRIS_PROJECT_ROOT")
        if env_root:
            project_root = Path(env_root)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # noqa: ANN202
        # Register mock AI responses when running in mock mode (GUI dev).
        if mock_enabled():
            _register_server_mock_responses()

        # Start file watcher as a background task if project root is known.
        stop = asyncio.Event()
        task = None
        if project_root is not None and ProjectPaths(project_root.resolve()).version_file.is_file():
            task = asyncio.create_task(watch_project(project_root.resolve(), stop))
        yield
        stop.set()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="latris API",
        version=latris.__version__,
        lifespan=lifespan,
    )

    # Perf telemetry — no-ops unless ``LATRIS_PERF=1`` is set. Installed
    # before CORS so it sees raw timing without preflight overhead.
    app.add_middleware(PerfMiddleware)

    # CORS — allow localhost origins for Vite dev server and Electron.
    # "null" is the Origin header value for file:// protocol (packaged Electron).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev
            "http://localhost:8741",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8741",
            "null",  # file:// protocol (packaged Electron)
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store the project root so the dependency (get_project_root) can read it.
    # Resolve to an absolute path once so every request gets a stable root
    # regardless of the process working directory.
    app.state.project_root = project_root.resolve() if project_root is not None else None

    # ── Exception handlers ────────────────────────────────────────────
    @app.exception_handler(NotAProjectError)
    async def _not_a_project(_request: Request, exc: NotAProjectError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_a_project", "detail": str(exc)})

    @app.exception_handler(IdentityError)
    async def _identity_error(_request: Request, exc: IdentityError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": "identity_error", "detail": str(exc)})

    @app.exception_handler(ResolveError)
    async def _resolve_error(_request: Request, exc: ResolveError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "resolve_error", "detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": str(exc)})

    @app.exception_handler(LookupError)
    async def _lookup_error(_request: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "lookup_error", "detail": str(exc)})

    @app.exception_handler(RuntimeError)
    async def _runtime_error(_request: Request, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"error": "llm_error", "detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        """Catch-all: always return JSON with the error detail so packaged-app
        users can diagnose issues (the default handler returns a bare
        'Internal Server Error' which is opaque)."""
        import traceback

        detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        return JSONResponse(status_code=500, content={"detail": detail})

    # ── Mutation route modules ────────────────────────────────────────
    app.include_router(activity.router)
    app.include_router(ai.router)
    app.include_router(analysis.router)
    app.include_router(annotations.router)
    app.include_router(checks.router)
    app.include_router(readiness.router)
    app.include_router(nodes.router)
    app.include_router(edges.router)
    app.include_router(attributes.router)
    app.include_router(references.router)
    app.include_router(evidence.router)
    app.include_router(provenance.router)
    app.include_router(challenges.router)
    app.include_router(views.router)
    app.include_router(view_attributes.router)
    app.include_router(model_types.router)
    app.include_router(model_choices.router)
    app.include_router(export.router)
    app.include_router(report_config.router)
    app.include_router(review.router)
    app.include_router(story.router)
    app.include_router(sync.router)
    app.include_router(fcm.router)
    app.include_router(bn.router)
    app.include_router(history.router)
    app.include_router(layout.router)
    app.include_router(lineage.router)
    app.include_router(datasets.router)
    app.include_router(findings.router)
    app.include_router(interpret.router)
    app.include_router(completeness.router)
    app.include_router(compose.router)
    app.include_router(configure.router)
    app.include_router(help_routes.router)

    # ── Read-only endpoints ───────────────────────────────────────────
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        root = app.state.project_root
        return {
            "status": "ok",
            "version": latris.__version__,
            "project_root": str(root) if root else None,
        }

    @app.get("/api/identity")
    def get_identity(root: Root) -> dict[str, Any]:
        from latris.repo.git import get_effective_identity

        name, email = get_effective_identity(root)
        return {"name": name, "email": email}

    @app.get("/api/project")
    def get_project(root: Root) -> dict[str, Any]:
        paths = ProjectPaths(root)
        foundation = load_model(ProjectFoundation, paths.project_yaml)
        return foundation.model_dump(mode="json")

    @app.patch("/api/project")
    def update_project(body: ProjectUpdateRequest, root: Root) -> dict[str, Any]:
        from latris.operations.batch import batch as _batch
        from latris.operations.commit import auto_commit
        from latris.operations.project import load_foundation, set_question, update_selected_models
        from latris.repo.git import head_sha
        from latris.repo.yaml_io import dump_model

        paths_ = ProjectPaths(root)
        _, foundation = load_foundation(root)

        dirty = False
        if body.name is not None and body.name != foundation.name:
            foundation.name = body.name
            dirty = True
        if body.background is not None and body.background != foundation.background:
            foundation.background = body.background
            dirty = True
        if body.boundary is not None and body.boundary != foundation.boundary:
            foundation.boundary = body.boundary
            dirty = True
        if body.exclusions is not None and body.exclusions != foundation.exclusions:
            foundation.exclusions = body.exclusions
            dirty = True
        if body.predictions is not None and body.predictions != foundation.predictions:
            foundation.predictions = body.predictions
            dirty = True
        if body.coverage_dimensions is not None and body.coverage_dimensions != foundation.coverage_dimensions:
            foundation.coverage_dimensions = body.coverage_dimensions
            dirty = True
        if body.granularity_level is not None and body.granularity_level != foundation.granularity_level:
            foundation.granularity_level = body.granularity_level
            dirty = True
        if body.audience is not None and body.audience != foundation.audience:
            foundation.audience = body.audience
            dirty = True

        statement_changed = body.statement is not None and body.statement != foundation.statement
        models_changed = (
            body.selected_model_types is not None and body.selected_model_types != foundation.selected_model_types
        )

        if not dirty and not statement_changed and not models_changed:
            return {"commit_sha": None}

        sha_before = head_sha(root)
        with _batch(root, subject=f"Updated project: {foundation.name or 'untitled'}"):
            if dirty:
                dump_model(foundation, paths_.project_yaml)
                auto_commit(
                    root, subject=f"Updated project: {foundation.name or 'untitled'}", paths=[paths_.project_yaml]
                )

            if statement_changed:
                set_question(root, body.statement)

            if models_changed:
                update_selected_models(body.selected_model_types, root=root)

        sha_after = head_sha(root)
        return {"commit_sha": sha_after if sha_after != sha_before else None}

    @app.get("/api/substrate")
    def get_substrate(root: Root) -> dict[str, Any]:
        paths = ProjectPaths(root)
        sub = load_model(Substrate, paths.conceptual_yaml)
        return sub.model_dump(mode="json")

    # /api/references and /api/challenges are handled by their route modules.

    @app.get("/api/state")
    def full_state(root: Root) -> dict[str, Any]:
        paths = ProjectPaths(root)
        return load_full_state(paths)

    # ── WebSocket ─────────────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            while True:
                # Keep the connection alive; client can send pings.
                await ws.receive_text()
        except Exception:  # noqa: BLE001
            manager.disconnect(ws)

    return app
