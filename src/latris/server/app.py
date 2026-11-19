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
from typing import Any

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import latris
from latris.ai.adapters import mock_enabled
from latris.ai.adapters.base import LLMCallError
from latris.operations._resolve import ResolveError
from latris.repo.git import GitError, IdentityError
from latris.repo.layout import ProjectPaths
from latris.repo.project import NotAProjectError
from latris.repo.yaml_io import load_model
from latris.schema import (
    ProjectFoundation,
    Substrate,
)
from latris.server.access import AccessTokenMiddleware, configured_token
from latris.server.deps import Root, log_unhandled, serialise_writes
from latris.server.perf import PerfMiddleware
from latris.server.routes import (
    activity,
    ai,
    analyses,
    analysis,
    annotations,
    attributes,
    build,
    challenges,
    checks,
    completeness,
    compose,
    configure,
    datasets,
    edges,
    evidence,
    export,
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
    results,
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


PLUGIN_ENTRY_POINT_GROUP = "latris.server_plugins"


def _register_plugins(app: FastAPI) -> None:
    """Let installed packages add routes to the server.

    Each entry point in the ``latris.server_plugins`` group must resolve to a
    callable taking the ``FastAPI`` app. ``LATRIS_SERVER_PLUGINS`` (comma-
    separated ``module:function``) names more, for builds where package
    metadata isn't available (frozen apps, slim containers). Plugins run after
    the built-in routers. A plugin that fails to load raises: a half-registered
    server is worse than one that refuses to start.
    """
    import importlib
    from importlib.metadata import entry_points

    loaded: set[str] = set()
    for ep in entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
        ep.load()(app)
        loaded.add(ep.value)
    for spec in os.environ.get("LATRIS_SERVER_PLUGINS", "").split(","):
        spec = spec.strip()
        if not spec or spec in loaded:
            continue
        module, _, attr = spec.partition(":")
        getattr(importlib.import_module(module), attr or "register")(app)
        loaded.add(spec)


def _include_formalism_routers(app: FastAPI) -> None:
    """Each registered formalism's routes (``operations/formalisms``), in registration order."""
    import importlib

    from latris.operations import formalisms

    for f in formalisms.all_formalisms():
        if f.routes:
            app.include_router(importlib.import_module(f.routes).router)


def create_app(*, project_root: Path | None = None, access_token: str | None = None) -> FastAPI:
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
            from latris.ai.adapters.mock_fixtures import register_gui_defaults

            register_gui_defaults()

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
        dependencies=[Depends(serialise_writes)],
    )

    # Perf telemetry — no-ops unless ``LATRIS_PERF=1`` is set. Installed
    # before CORS so it sees raw timing without preflight overhead.
    app.add_middleware(PerfMiddleware)

    # Optional shared-secret gate (LATRIS_SERVER_TOKEN). Added before CORS so
    # CORS stays outermost: preflights are answered and 401s carry headers.
    token = access_token if access_token is not None else configured_token()
    if token:
        app.add_middleware(AccessTokenMiddleware, token=token)

    # CORS — allow localhost origins for the Vite dev server only.
    # Never "null": sandboxed iframes on *any* website send Origin: null,
    # so allowing it lets arbitrary pages drive this API. (It was for the
    # packaged Electron app's file:// pages; that app is retired.)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev
            "http://localhost:8741",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8741",
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
        # A refusal from the domain ("only a leaf takes a probability").
        # (Malformed request bodies are answered 422 by FastAPI before this.)
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": str(exc)})

    @app.exception_handler(LookupError)
    async def _lookup_error(_request: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc)})

    @app.exception_handler(LLMCallError)
    async def _llm_error(_request: Request, exc: LLMCallError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"error": "llm_error", "detail": str(exc)})

    @app.exception_handler(GitError)
    async def _git_error(_request: Request, exc: GitError) -> JSONResponse:
        error_id = log_unhandled(exc, "git failed")
        return JSONResponse(
            status_code=500,
            content={"error": "git_error", "detail": f"Saving the change failed (error id {error_id})."},
        )

    @app.exception_handler(RuntimeError)
    async def _runtime_error(_request: Request, exc: RuntimeError) -> JSONResponse:
        # Raised with a message meant for the person ("needs the 'quant' extra").
        return JSONResponse(status_code=500, content={"error": "runtime_error", "detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        """Catch-all: JSON with a short message and an error id.

        The traceback goes to the server log under that id, never to the
        client — it exposes paths, code and environment details.
        """
        error_id = log_unhandled(exc)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": f"{type(exc).__name__}: {exc}", "error_id": error_id},
        )

    # ── Mutation route modules ────────────────────────────────────────
    app.include_router(activity.router)
    app.include_router(ai.router)
    app.include_router(analyses.router)
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
    app.include_router(story.router)
    app.include_router(sync.router)
    _include_formalism_routers(app)
    app.include_router(results.router)
    app.include_router(history.router)
    app.include_router(layout.router)
    app.include_router(lineage.router)
    app.include_router(datasets.router)
    app.include_router(findings.router)
    app.include_router(build.router)
    app.include_router(interpret.router)
    app.include_router(completeness.router)
    app.include_router(compose.router)
    app.include_router(configure.router)
    app.include_router(help_routes.router)
    _register_plugins(app)

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
        from latris.operations.project import update_foundation

        fields = body.model_dump(exclude={"statement", "selected_model_types"})
        sha = update_foundation(
            fields, statement=body.statement, selected_model_types=body.selected_model_types, root=root
        )
        return {"commit_sha": sha}

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
