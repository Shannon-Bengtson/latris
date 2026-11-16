"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import Request

from latris.repo.layout import ProjectPaths
from latris.repo.project import NotAProjectError, find_project_root


def get_project_root(request: Request) -> Path:
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


def log_unhandled(exc: BaseException, message: str = "Unhandled server error") -> str:
    """Log *exc* with its traceback under a fresh error id and return the id.

    Clients get the id, never the traceback; the id finds it in the log.
    """
    error_id = uuid.uuid4().hex[:12]
    logging.getLogger("latris.server").error("%s [error_id=%s]", message, error_id, exc_info=exc)
    return error_id
