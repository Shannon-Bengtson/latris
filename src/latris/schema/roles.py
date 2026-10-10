"""View roles — formalism-specific classifications for substrate entities.

Roles are assigned per (entity, model_type) pair.  They classify what
a generic substrate entity *means* within a particular formal view.
E.g., a substrate ``variable`` might have role ``stock`` in a System
Dynamics view, or role ``chance`` in a Bayesian Network view.

Roles participate in the same provenance lifecycle as other attributes:
they carry maturity, origin, verification, informants, and can be
contested.  This matters because classification decisions (is this a
stock or an auxiliary?) are genuine modelling judgements.
"""

from __future__ import annotations

from pydantic import Field

from latris.schema.attributes import _Base, _EntryBase


class RoleEntry(_EntryBase):
    """A role assignment: entity X has role Y within a model-type view."""

    attribute: str = "role"
    value: str  # The role name, e.g. "stock", "gate", "place"


class RoleSet(_Base):
    """All role assignments for a single model type."""

    entries: list[RoleEntry] = Field(default_factory=list)
