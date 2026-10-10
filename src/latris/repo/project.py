"""Project discovery and handle.

``find_project_root`` walks upward from a starting directory looking for the
marker ``.graph-tooling/version`` file that init lays down.
"""

from __future__ import annotations

from pathlib import Path

from latris.repo.layout import STATE_DIR_NAME, VERSION_FILE_NAME, ProjectPaths


class NotAProjectError(RuntimeError):
    """Raised when no latris project is found at or above a path."""


def find_project_root(start: Path | None = None) -> Path | None:
    """Return the project root for ``start`` (defaults to cwd), or ``None`` if none.

    A project root is the first ancestor directory containing
    ``<root>/.graph-tooling/version``.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / STATE_DIR_NAME / VERSION_FILE_NAME).is_file():
            return candidate
    return None


def require_project(start: Path | None = None) -> ProjectPaths:
    """Return ``ProjectPaths`` or raise ``NotAProjectError``."""
    root = find_project_root(start)
    if root is None:
        raise NotAProjectError("not inside a latris project. Run `latris init <name>` to create one.")
    return ProjectPaths(root)
