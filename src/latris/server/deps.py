"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from latris.operations import write_lock
from latris.repo.layout import ProjectPaths
from latris.repo.project import NotAProjectError, find_project_root


def get_project_root(request: HTTPConnection) -> Path:
    """Return the project root path from app state or discovery."""
    root: Path | None = request.app.state.project_root
    if root is not None:
        resolved = root.resolve()
        paths = ProjectPaths(resolved)
        if not paths.version_file.is_file():
            raise NotAProjectError(f"not a latris project: {resolved}")
        return resolved

    found = find_project_root()
    if found is None:
        raise NotAProjectError("not inside a latris project. Run `latris init <name>` to create one.")
    return found


Root = Annotated[Path, Depends(get_project_root)]
"""The project root, injected — the type every route takes its root as."""

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def serialise_writes(connection: HTTPConnection) -> AsyncIterator[None]:
    """App-wide dependency: one mutating request at a time per project.

    See :mod:`latris.operations.write_lock`. Reads (GET) and WebSockets run
    freely; a request with no project to lock runs unlocked.
    """
    if connection.scope["type"] != "http" or connection.scope["method"] not in _MUTATING:
        yield
        return
    try:
        root = get_project_root(connection)  # type: ignore[arg-type]
    except NotAProjectError:
        yield
        return
    async with write_lock.hold(root):
        yield


def log_unhandled(exc: BaseException, message: str = "Unhandled server error") -> str:
    """Log *exc* with its traceback under a fresh error id and return the id.

    Clients get the id, never the traceback; the id finds it in the log.
    """
    error_id = uuid.uuid4().hex[:12]
    logging.getLogger("latris.server").error("%s [error_id=%s]", message, error_id, exc_info=exc)
    return error_id
