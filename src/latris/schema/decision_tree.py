"""Decision tree schema — branch labels, probabilities and values; payoffs; uncertainties; the objective.

A decision tree lives on the ordinary substrate: its nodes are entities with a
view role (``views/roles/decision_tree-roles.yaml``: ``decision``, ``chance``
or ``terminal``) and its branches are ordinary edges from parent to child.
The numbers are stored per value, each with provenance (``EntryBase``):

- ``views/parameters/decision_tree-branch.yaml``  — :class:`DTBranchSet`: a
  branch's label (the option or the state), its probability (chance branches)
  and any value incurred along it (e.g. the cost of a test);
- ``views/parameters/decision_tree-payoff.yaml``  — :class:`DTPayoffSet`: the
  value at a terminal node;
- ``views/parameters/decision_tree-chance.yaml``  — :class:`DTChanceSet`: the
  uncertainty a chance node resolves, so chance nodes that are the same
  uncertainty under different choices can be priced together (EVPI);
- ``views/parameters/decision_tree-settings.yaml`` — :class:`DTSettings`:
  whether the best choice maximises or minimises, and the units.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from latris.schema.attributes import EntryBase, _Base

DTElement = Literal["decision", "chance", "terminal"]
DT_ELEMENTS: tuple[str, ...] = ("decision", "chance", "terminal")


class DTBranchEntry(EntryBase):
    """A branch (``target_id`` is the edge, parent → child)."""

    attribute: str = "branch"
    label: str | None = None  # the option (from a decision) or the state (from a chance node)
    probability: float | None = Field(default=None, ge=0.0, le=1.0)  # chance branches only
    value: float = 0.0  # incurred along the branch, in the tree's units (e.g. a cost as a negative value)
    notes: str | None = None


class DTBranchSet(_Base):
    entries: list[DTBranchEntry] = Field(default_factory=list)


class DTPayoffEntry(EntryBase):
    """The value at a terminal node, in the tree's units."""

    attribute: str = "payoff"
    value: float
    notes: str | None = None


class DTPayoffSet(_Base):
    entries: list[DTPayoffEntry] = Field(default_factory=list)


class DTChanceEntry(EntryBase):
    """Names the uncertainty a chance node resolves (default: the node's label)."""

    attribute: str = "chance"
    uncertainty: str


class DTChanceSet(_Base):
    entries: list[DTChanceEntry] = Field(default_factory=list)


class DTSettings(_Base):
    objective: Literal["maximise", "minimise"] = "maximise"
    units: str | None = None
