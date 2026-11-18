"""Option pieces the CLI commands share, built from the schema so they can't drift from it."""

from __future__ import annotations

from typing import get_args

from latris.schema.common import ProvenanceOrigin, ProvenanceVerification

ORIGIN_HELP = "Where it came from: " + " | ".join(get_args(ProvenanceOrigin)) + "."


def verification(verified: bool) -> ProvenanceVerification:
    """The provenance verification a ``--verified`` flag stands for."""
    return "human-verified" if verified else "unverified"
