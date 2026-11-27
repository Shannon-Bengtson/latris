"""Where a CLI command or server route sits in the workflow structure (``schema/workflow.py``).

Each command module (``cli/*_cmd.py``) and route module (``server/routes/*.py``) declares ``PLACE``:

- a string, when every command or route in it has the same place (``PLACE = "evidence"``);
- or a dict from function name to place, with ``"*"`` for the module's default
  (``PLACE = {"*": "formalise.values", "check": "validation"}``).

A route built by a shared factory (one function serving several model types) carries its place itself, in
its OpenAPI extras as ``x-latris-place``; that wins over the module's declaration.

A place is a step (``"analyse.uncertainty"``), a stage as a whole (``"analyse"``, for something that serves
every step of it), a track (``"evidence"``), or ``"composite"``. Placement follows the rules in
``docs/engineering/WORKFLOW_STRUCTURE.md``; ``tests/test_places.py`` fails for a command or route with no
place, or one not in the registry.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from latris.schema.workflow import is_place


def declared_place(func: Callable[..., Any]) -> str | None:
    """The place ``func``'s module declares for it, or None if it declares none."""
    module = sys.modules.get(getattr(func, "__module__", "") or "")
    spec = getattr(module, "PLACE", None)
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        return spec.get(getattr(func, "__name__", ""), spec.get("*"))
    return None


def place_of(func: Callable[..., Any]) -> str:
    """``func``'s place; a ValueError if it has none or names one the registry doesn't have."""
    place = declared_place(func)
    if place is None:
        raise ValueError(f"{func.__module__}.{func.__name__} declares no workflow place (PLACE)")
    if not is_place(place):
        raise ValueError(f"{func.__module__}.{func.__name__}: {place!r} is not a workflow place")
    return place


def cli_places() -> list[tuple[str, str | None]]:
    """(command path, declared place) for every CLI command, e.g. ("sd monte-carlo", "analyse.uncertainty")."""
    from typer.main import get_command

    from latris.cli.app import app

    out: list[tuple[str, str | None]] = []

    def walk(command: Any, path: list[str]) -> None:
        subs = getattr(command, "commands", None)
        if subs:
            for name, sub in subs.items():
                walk(sub, [*path, name])
        elif command.callback is not None:
            out.append((" ".join(path), declared_place(command.callback)))

    walk(get_command(app), [])
    return out


def route_places(app: Any) -> list[tuple[str, str, str | None]]:
    """(method, path, declared place) for every route of a latris server app."""
    from fastapi.routing import APIRoute

    out: list[tuple[str, str, str | None]] = []

    def walk(routes: Any) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                # A route built by a shared factory carries its own place; otherwise its module declares it.
                place = (route.openapi_extra or {}).get("x-latris-place") or declared_place(route.endpoint)
                for method in sorted(route.methods or ()):
                    out.append((method, route.path, place))
                continue
            # An included router (FastAPI wraps it; its routes already carry the prefix).
            inner = getattr(route, "original_router", None) or getattr(route, "router", None)
            if inner is not None and getattr(inner, "routes", None) is not None:
                walk(inner.routes)

    walk(app.router.routes)
    return out


def composite_places(func: Callable[..., Any]) -> tuple[str, ...]:
    """The places a composite command or route can carry out: its module's ``CARRIES``."""
    module = sys.modules.get(getattr(func, "__module__", "") or "")
    return tuple(getattr(module, "CARRIES", ()))


INDEX_START = "<!-- commands-by-place:start (generated: python scripts/gen_cli_index.py) -->"
INDEX_END = "<!-- commands-by-place:end -->"


def cli_index_markdown() -> str:
    """Every CLI command grouped by stage and step, then by track, as the CLI reference's index."""
    from latris.schema import workflow as wf

    by_place: dict[str, list[str]] = {}
    for command, place in cli_places():
        by_place.setdefault(place or "", []).append(command)

    def row(name: str, place: str) -> str:
        cmds = ", ".join(f"`{c}`" for c in sorted(by_place.get(place, [])))
        return f"| {name} | {cmds} |" if cmds else ""

    lines = ["| Place | Commands |", "|---|---|"]
    for stage in wf.stages():
        lines.append(row(f"**{stage.name}**", stage.id))
        for st in stage.steps:
            lines.append(row(f"{stage.name}: {st.name}", st.id))
    for track in wf.TRACKS:
        lines.append(row(f"*{track.name}* (track)", track.id))
    lines.append(row("Composite", wf.COMPOSITE))
    return "\n".join(line for line in lines if line) + "\n"
