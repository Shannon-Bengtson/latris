"""Unified maturity ladder.

A single 3-step workflow gate applied uniformly to every modelling
artifact (Entity, Edge, Finding, Mapping, LineageNode, Milestone).
Replaces the 9-step attribute-level ``MaturityLevel`` and the parallel
status fields previously scattered across ``Finding``, ``Mapping``,
``LineageNode``, and ``Milestone``. Full design in
``docs/design/MATURITY_LADDER.md``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Maturity = Literal["proposed", "reviewed", "approved"]

MATURITY_ORDER: tuple[Maturity, ...] = ("proposed", "reviewed", "approved")


class MaturityBadges(BaseModel):
    """Derived facts about an artifact, computed at fetch time.

    Never persisted. The canonical source for each badge is the
    related store (EvidenceLink, Challenge, FloatSet, formalism
    field, Prediction). Surfaced in the GUI as small icons next to
    the maturity chip — passive signal, not a workflow click.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    has_evidence: bool = False
    has_challenges: bool = False
    has_formalism: bool = False
    has_quantification: bool = False
    has_confirmed_prediction: bool = False
