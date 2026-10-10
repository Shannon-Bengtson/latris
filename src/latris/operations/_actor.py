"""Shared actor resolution for operations that record human provenance.

Most operations stamp the responsible human by reading the configured git
identity. This is the single home for that ``ensure_identity`` → ``HumanActor``
step, replacing the per-module ``_author`` copies.

Note: ``analysis_runs`` and ``datasets`` deliberately use different identity
sources (``get_effective_identity`` / ``head_author``); they do not use this.
"""

from __future__ import annotations

from pathlib import Path

from latris.repo import git
from latris.schema import HumanActor


def author(root: Path) -> HumanActor:
    """The responsible human, from the configured git identity."""
    name, email = git.ensure_identity(root)
    return HumanActor(name=name, email=email)
