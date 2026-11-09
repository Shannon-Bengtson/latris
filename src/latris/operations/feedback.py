"""Feedback structure across views: causal links plus the stock-and-flow structure of an SD view.

A causal loop diagram and a system dynamics model can share one substrate, but
their feedback is drawn differently. In the diagram, feedback is a cycle of
causal links; in SD, much of it runs through a stock: a flow edge
``stock → outflow`` carries material out, and the outflow's equation reads the
stock (more water, faster drain), which closes a loop that has no causal-edge
cycle at all. Loop analysis on causal edges alone therefore misses every loop
through a stock, and the "one model, several views" promise breaks.

:func:`feedback_edges` adds that structure for loop analysis:

- an inflow (flow edge ``flow → stock``) raises its stock: ``+``;
- an outflow (flow edge ``stock → flow``) is kept as the stock driving the drain,
  plus a synthetic return edge ``flow → stock`` (id ``<edge>:drain``): ``−``.

:func:`link_polarity` gives those links (and any SD information link the diagram
has no polarity for) a sign: drains are ``−``, inflows ``+``, and an equation's
dependence on an input is read off the compiled model — a small change in the
input, the change in the result — so "more water, faster drain" comes out ``+``.
A polarity stated on the diagram always wins. If the SD model doesn't compile,
those links stay unsigned and the loops through them are "unknown".
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from latris.operations.graph_analysis import causal_edges
from latris.repo.layout import ProjectPaths

DRAIN = ":drain"


@dataclass(frozen=True)
class FeedbackEdge:
    id: str
    from_id: str
    to_id: str
    kind: str = "causal"


def _sd_roles(paths: ProjectPaths) -> dict[str, str]:
    path = paths.role_path("sd")
    if not path.exists():
        return {}
    from latris.repo.yaml_io import load_model
    from latris.schema.roles import RoleSet

    return {e.target_id: e.value for e in load_model(RoleSet, path).entries}


def feedback_edges(edges: list[Any], paths: ProjectPaths | None) -> list[Any]:
    """Causal edges, plus the stock-and-flow edges that carry feedback when the project has an SD view."""
    causal = causal_edges(edges)
    roles = _sd_roles(paths) if paths is not None else {}
    if not roles:
        return causal
    out: list[Any] = list(causal)
    for e in edges:
        if e.kind != "flow":
            continue
        a, b = roles.get(e.from_id), roles.get(e.to_id)
        if a == "flow" and b == "stock":
            out.append(e)
        elif a == "stock" and b == "flow":
            out.append(e)
            out.append(FeedbackEdge(f"{e.id}{DRAIN}", e.to_id, e.from_id))
    return out


def link_polarity(edges: list[Any], paths: ProjectPaths | None) -> dict[str, str]:
    """Signs for stock-and-flow links and unsigned SD information links (diagram polarity takes precedence)."""
    roles = _sd_roles(paths) if paths is not None else {}
    if not roles:
        return {}
    out: dict[str, str] = {}
    for e in edges:
        if e.kind != "flow":
            continue
        a, b = roles.get(e.from_id), roles.get(e.to_id)
        if a == "flow" and b == "stock":
            out[e.id] = "+"
        elif a == "stock" and b == "flow":
            out[f"{e.id}{DRAIN}"] = "-"
    signs = _equation_signs(paths) if paths is not None else {}
    for e in edges:
        sign = signs.get((e.from_id, e.to_id))
        if sign and e.id not in out:
            out[e.id] = sign
    return out


def _equation_signs(paths: ProjectPaths) -> dict[tuple[str, str], str]:
    from latris.operations.analysis_results import fingerprint

    try:
        key = fingerprint(paths, "sd")
    except Exception:  # noqa: BLE001 - a fingerprint failure just means no signs
        return {}
    return dict(_signs_cached(str(paths.root), key))


@lru_cache(maxsize=32)
def _signs_cached(root: str, _fingerprint: str) -> tuple[tuple[tuple[str, str], str], ...]:
    """Sign of each equation's response to each of its inputs, at the start of the run."""
    from pathlib import Path

    from latris.operations import sd as sd_ops
    from latris.operations.sd_inference import fast_model

    try:
        model = sd_ops.compile_project(root=Path(root))
    except Exception:  # noqa: BLE001 - an incomplete SD model has no signs to offer
        return ()
    fast = fast_model(model)
    if fast is None:
        return ()
    t0 = model.settings.initial_time
    y0 = [model.initial[s] for s in model.stocks]
    consts = fast.constants_vector(model)
    try:
        computed = fast.values(t0, y0, consts)
    except Exception:  # noqa: BLE001
        return ()
    env: dict[str, float] = {}
    for s, y in zip(model.stocks, y0, strict=True):
        env[model.slugs[s]] = y * fast.stock_factor[s]
    for c, v in zip(fast.const_ids, consts, strict=True):
        env[model.slugs[c]] = v
    for v, x in zip(model.order, computed, strict=True):
        env[model.slugs[v]] = x
    by_slug = {slug: i for i, slug in model.slugs.items()}
    tb = t0 * fast.time_factor
    out: list[tuple[tuple[str, str], str]] = []
    for z in model.order:
        eq = fast.equation[z]
        try:
            base = eq(tb, env)
        except Exception:  # noqa: BLE001
            continue
        for name in model.equations[z].names:
            x = by_slug.get(name)
            if x is None or name not in env:
                continue
            h = max(abs(env[name]) * 1e-6, 1e-12)
            try:
                bumped = eq(tb, {**env, name: env[name] + h})
            except Exception:  # noqa: BLE001
                continue
            delta = bumped - base
            if abs(delta) > 1e-12 * max(1.0, abs(base)):
                out.append(((x, z), "+" if delta > 0 else "-"))
    return tuple(out)
