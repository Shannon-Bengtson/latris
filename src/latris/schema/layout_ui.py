"""Canvas layout models — UI metadata (positions, sizes), not domain data."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NodeLayout(BaseModel):
    """Canvas position and optional size of a single node."""

    x: float
    y: float
    width: float | None = None
    height: float | None = None


class EdgeLayout(BaseModel):
    """Routing for a single edge — ordered waypoints (each ``{"x", "y"}``)."""

    waypoints: list[dict[str, float]] = Field(default_factory=list)


class CanvasLayout(BaseModel):
    """The whole canvas: per-node positions and per-edge routing, keyed by id."""

    nodes: dict[str, NodeLayout] = Field(default_factory=dict)
    edges: dict[str, EdgeLayout] = Field(default_factory=dict)
