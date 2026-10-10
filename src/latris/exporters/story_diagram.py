"""Self-contained SVG renderer for the Story diagram.

Renders the model as a node-link SVG **without any external binary** (no
graphviz), reusing the canvas's persisted layout (``layout/canvas.layout.yaml``)
and the GUI's visual language — kind colours, kind badges, polarity-coloured
arrows, per-kind dash patterns. The published story therefore matches what the
modeller arranged on the build canvas, and renders identically on every install.

Every node group is ``<g class="node" id="{entity_id}">`` and every edge group
``<g class="edge" id="{edge_id}">`` so the scroll-driven emphasis controller in
``story.html.jinja2`` (which toggles ``story-emph``/``story-dim`` by element id)
keeps working. The outer node shape is a rounded-rect ``<path>`` so the existing
``.story-emph path`` CSS highlights it with no stylesheet changes.

When the project has no saved canvas layout (e.g. never opened in the GUI), a
simple layered auto-layout is computed so the diagram still renders.

Constants mirror ``gui/src/theme.ts`` — keep them in sync if the canvas look
changes. See docs/design/STORY.md.
"""

from __future__ import annotations

from html import escape

from latris.exporters._scope import view_member_ids
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import PolaritySet, Substrate
from latris.schema.layout_ui import CanvasLayout

# ── Visual constants (mirror gui/src/theme.ts) ───────────────────────────
_KIND_COLORS = {
    "concept": "#2a6b5e",
    "variable": "#3d8b7a",
    "event": "#c9845e",
    "actor": "#5a9a6e",
    "state": "#6a8a9e",
    "decision": "#a06840",
    "hazard": "#c04040",
}
_KIND_LABELS = {
    "concept": "C",
    "variable": "V",
    "event": "E",
    "actor": "A",
    "state": "S",
    "decision": "D",
    "hazard": "H",
}
# SVG stroke-dasharray per edge kind ("0" = solid → no dasharray attr).
_EDGE_KIND_DASH = {
    "causal": "0",
    "conditional": "6 3",
    "temporal": "2 3",
    "decomposition": "0",
    "decision_rule": "1 4",
    "governance": "1 4",
    "definitional": "5 2 1 2",
    "informational": "4 2",
    "flow": "8 3",
    "support": "4 4",
    "logical": "0",
    "association": "3 3",
}
_POLARITY_COLORS = {"+": "#2a6b5e", "-": "#c04040"}
_EDGE_DEFAULT_COLOR = "#6a7a72"
_KIND_FALLBACK_COLOR = "#6a7a72"

_CANVAS_BG = "#f4f1eb"
_TEXT_PRIMARY = "#1c2420"
_NODE_W = 160.0
_NODE_H = 60.0
_NODE_RADIUS = 8.0
_FONT_STACK = '-apple-system,"Segoe UI",system-ui,Roboto,Helvetica,Arial,sans-serif'
_PAD = 48.0  # viewBox padding around the content bounds


def _rounded_rect_path(x: float, y: float, w: float, h: float, r: float) -> str:
    """SVG path 'd' for a rounded rectangle (used so .story-emph path applies)."""
    r = min(r, w / 2, h / 2)
    return (
        f"M{x + r:.1f},{y:.1f} H{x + w - r:.1f} A{r:.1f},{r:.1f} 0 0 1 {x + w:.1f},{y + r:.1f} "
        f"V{y + h - r:.1f} A{r:.1f},{r:.1f} 0 0 1 {x + w - r:.1f},{y + h:.1f} "
        f"H{x + r:.1f} A{r:.1f},{r:.1f} 0 0 1 {x:.1f},{y + h - r:.1f} "
        f"V{y + r:.1f} A{r:.1f},{r:.1f} 0 0 1 {x + r:.1f},{y:.1f} Z"
    )


# ── Orthogonal edge routing (ports gui/src/layout/orthogonal-path.ts) ─────
# The build canvas routes edges with right-angle (Manhattan) segments and
# rounded corners, departing/arriving on the node side that faces the other
# node. We replicate that here so the published diagram matches the canvas
# rather than drawing straight diagonals.
_EDGE_RADIUS = 8.0  # radii.edge in theme.ts
Pt = tuple[float, float]


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _side_anchor(geom: tuple[float, float, float, float], side: str) -> Pt:
    """Mid-point of a node side ('L'/'R'/'T'/'B')."""
    x, y, w, h = geom
    cx, cy = x + w / 2, y + h / 2
    return {
        "L": (x, cy),
        "R": (x + w, cy),
        "T": (cx, y),
        "B": (cx, y + h),
    }[side]


def _pick_side(center: Pt, toward: Pt) -> str:
    """Which node side faces ``toward`` — the handle the canvas would auto-pick."""
    dx, dy = toward[0] - center[0], toward[1] - center[1]
    if abs(dx) >= abs(dy):
        return "R" if dx > 0 else "L"
    return "B" if dy > 0 else "T"


def _default_bends(source: Pt, target: Pt, s_side: str, t_side: str) -> list[Pt]:
    """computeDefaultBendPoints — the smooth-step route used when no waypoints."""
    mid_y = (source[1] + target[1]) / 2
    mid_x = (source[0] + target[0]) / 2
    s_vert, t_vert = s_side in ("T", "B"), t_side in ("T", "B")
    if s_vert and t_vert:
        return [(source[0], mid_y), (target[0], mid_y)]
    if not s_vert and not t_vert:
        return [(mid_x, source[1]), (mid_x, target[1])]
    if s_vert:
        return [(source[0], target[1])]
    return [(target[0], source[1])]


def _orthogonal_points(source: Pt, target: Pt, waypoints: list[Pt], s_side: str, t_side: str) -> list[Pt]:
    """buildOrthogonalPath's corner logic → the list of sharp bend points."""
    eps = 0.5
    dep = {"L": "h", "R": "h", "T": "v", "B": "v"}
    perp = {"h": "v", "v": "h"}
    corners = [source, *waypoints, target]
    raw: list[Pt] = [source]
    prev: str | None = None
    n = len(corners)
    for k in range(n - 1):
        frm, to = corners[k], corners[k + 1]
        aligned_h = abs(frm[1] - to[1]) <= eps
        aligned_v = abs(frm[0] - to[0]) <= eps
        if aligned_h or aligned_v:
            raw.append(to)
            if aligned_v and not aligned_h:
                prev = "v"
            elif aligned_h and not aligned_v:
                prev = "h"
            continue
        if k == 0:
            axis = dep[s_side]
        elif k == n - 2:
            axis = perp[dep[t_side]]
        else:
            axis = perp[prev] if prev else dep[s_side]
        bend = (to[0], frm[1]) if axis == "h" else (frm[0], to[1])
        raw.append(bend)
        raw.append(to)
        prev = perp[axis]
    pts: list[Pt] = [raw[0]]
    for p in raw[1:]:
        q = pts[-1]
        if abs(q[0] - p[0]) > eps or abs(q[1] - p[1]) > eps:
            pts.append(p)
    return pts


def _rounded_path(points: list[Pt], radius: float = _EDGE_RADIUS) -> str:
    """buildRoundedPathString — SVG 'd' with quadratic-bezier rounded corners."""
    if not points:
        return ""
    first = points[0]
    if len(points) == 1:
        return f"M {first[0]:.1f} {first[1]:.1f}"
    d = f"M {first[0]:.1f} {first[1]:.1f}"
    if radius <= 0 or len(points) == 2:
        return d + "".join(f" L {p[0]:.1f} {p[1]:.1f}" for p in points[1:])
    for i in range(1, len(points) - 1):
        prev, cur, nxt = points[i - 1], points[i], points[i + 1]
        in_dx, in_dy = _sign(cur[0] - prev[0]), _sign(cur[1] - prev[1])
        out_dx, out_dy = _sign(nxt[0] - cur[0]), _sign(nxt[1] - cur[1])
        in_len = abs(cur[0] - prev[0]) + abs(cur[1] - prev[1])
        out_len = abs(nxt[0] - cur[0]) + abs(nxt[1] - cur[1])
        if (in_dx == out_dx and in_dy == out_dy) or in_len < 1 or out_len < 1:
            d += f" L {cur[0]:.1f} {cur[1]:.1f}"
            continue
        r = min(radius, in_len / 2, out_len / 2)
        d += (
            f" L {cur[0] - in_dx * r:.1f} {cur[1] - in_dy * r:.1f}"
            f" Q {cur[0]:.1f} {cur[1]:.1f} {cur[0] + out_dx * r:.1f} {cur[1] + out_dy * r:.1f}"
        )
    last = points[-1]
    return d + f" L {last[0]:.1f} {last[1]:.1f}"


def _route_edge(s_geom, t_geom, waypoints: list[Pt]) -> tuple[str, Pt]:
    """Return (rounded SVG path, label point) for an edge, matching the canvas."""
    scx, scy = s_geom[0] + s_geom[2] / 2, s_geom[1] + s_geom[3] / 2
    tcx, tcy = t_geom[0] + t_geom[2] / 2, t_geom[1] + t_geom[3] / 2
    s_side = _pick_side((scx, scy), waypoints[0] if waypoints else (tcx, tcy))
    t_side = _pick_side((tcx, tcy), waypoints[-1] if waypoints else (scx, scy))
    s_anchor = _side_anchor(s_geom, s_side)
    t_anchor = _side_anchor(t_geom, t_side)
    wps = waypoints if waypoints else _default_bends(s_anchor, t_anchor, s_side, t_side)
    pts = _orthogonal_points(s_anchor, t_anchor, wps, s_side, t_side)
    mid = max(0, (len(pts) - 1) // 2)
    a, b = pts[mid], pts[min(mid + 1, len(pts) - 1)]
    return _rounded_path(pts), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _truncate(label: str, width: float) -> str:
    """Truncate a node label to roughly fit the node's inner width."""
    max_chars = max(3, int((width - 44.0) / 7.0))
    if len(label) <= max_chars:
        return label
    return label[: max_chars - 1].rstrip() + "…"


def _auto_layout(entity_ids: list[str], edges: list[tuple[str, str]]) -> dict[str, tuple[float, float]]:
    """Simple left-to-right layered layout when no canvas layout is saved.

    Longest-path layering (cycle-safe via an iteration cap), nodes ordered
    within a layer by first appearance. Returns top-left positions.
    """
    layer = dict.fromkeys(entity_ids, 0)
    adj = [(s, t) for s, t in edges if s in layer and t in layer and s != t]
    for _ in range(len(entity_ids)):
        changed = False
        for s, t in adj:
            if layer[t] < layer[s] + 1:
                layer[t] = layer[s] + 1
                changed = True
        if not changed:
            break
    by_layer: dict[int, list[str]] = {}
    for nid in entity_ids:  # preserve substrate order within each column
        by_layer.setdefault(layer[nid], []).append(nid)
    positions: dict[str, tuple[float, float]] = {}
    for col, ids in sorted(by_layer.items()):
        for row, nid in enumerate(ids):
            positions[nid] = (col * (_NODE_W + 90.0), row * (_NODE_H + 50.0))
    return positions


def render_story_svg(paths: ProjectPaths, model_type: str) -> str | None:
    """Render the model for ``model_type`` to a self-contained SVG string.

    Returns ``None`` when the view has no entities (caller falls back).
    """
    substrate = load_model(Substrate, paths.conceptual_yaml)

    member_ids = view_member_ids(paths, model_type)
    if member_ids is not None:
        entities = [e for e in substrate.entities if e.id in member_ids]
        edges = [e for e in substrate.edges if e.id in member_ids]
    else:
        entities = list(substrate.entities)
        edges = list(substrate.edges)
    if not entities:
        return None

    # Polarity (CLD views colour + label edges by sign).
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()
    polarity = {e.target_id: e.value for e in pol_set.entries if e.attribute == "polarity"}

    # Positions + sizes from the persisted canvas layout; auto-layout if absent.
    layout_file = paths.layout_dir / "canvas.layout.yaml"
    layout = load_model(CanvasLayout, layout_file) if layout_file.exists() else CanvasLayout()

    entity_ids = [e.id for e in entities]
    have_all = all(nid in layout.nodes for nid in entity_ids)
    auto = {} if have_all else _auto_layout(entity_ids, [(e.from_id, e.to_id) for e in edges])

    geom: dict[str, tuple[float, float, float, float]] = {}  # id -> (x, y, w, h)
    for e in entities:
        nl = layout.nodes.get(e.id)
        if nl is not None:
            x, y = nl.x, nl.y
            w = nl.width or _NODE_W
            h = nl.height or _NODE_H
        else:
            x, y = auto.get(e.id, (0.0, 0.0))
            w, h = _NODE_W, _NODE_H
        geom[e.id] = (x, y, w, h)

    # Content bounds → viewBox.
    xs0 = [g[0] for g in geom.values()]
    ys0 = [g[1] for g in geom.values()]
    xs1 = [g[0] + g[2] for g in geom.values()]
    ys1 = [g[1] + g[3] for g in geom.values()]
    min_x, min_y = min(xs0) - _PAD, min(ys0) - _PAD
    vb_w, vb_h = (max(xs1) - min_x + _PAD), (max(ys1) - min_y + _PAD)

    # Arrow markers — one per distinct edge colour.
    edge_colors: dict[str, str] = {}  # edge_id -> colour
    for e in edges:
        sign = polarity.get(e.id)
        edge_colors[e.id] = _POLARITY_COLORS.get(sign, _EDGE_DEFAULT_COLOR)
    marker_id = {c: f"story-arrow-{i}" for i, c in enumerate(sorted(set(edge_colors.values())))}

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.1f} {min_y:.1f} '
        f'{vb_w:.1f} {vb_h:.1f}" width="{vb_w:.0f}" height="{vb_h:.0f}" '
        f'font-family=\'{_FONT_STACK}\'>'
    )
    parts.append("<defs>")
    for color, mid in marker_id.items():
        parts.append(
            f'<marker id="{mid}" markerWidth="11" markerHeight="11" viewBox="0 0 12 12" '
            f'refX="9" refY="6" orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
            f'<path d="M2,2 L10,6 L2,10 Z" fill="{color}"/></marker>'
        )
    parts.append("</defs>")

    # Edges first so nodes paint on top — routed orthogonally like the canvas,
    # following saved waypoints when present.
    saved_wps = {
        eid: [(wp["x"], wp["y"]) for wp in el.waypoints]
        for eid, el in layout.edges.items()
    }
    for e in edges:
        s = geom.get(e.from_id)
        t = geom.get(e.to_id)
        if s is None or t is None or e.from_id == e.to_id:
            continue
        path_d, (lx, ly) = _route_edge(s, t, saved_wps.get(e.id, []))
        color = edge_colors[e.id]
        dash = _EDGE_KIND_DASH.get(e.kind, "0")
        dash_attr = f' stroke-dasharray="{dash}"' if dash != "0" else ""
        parts.append(f'<g class="edge" id="{escape(e.id, quote=True)}">')
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="1.6"'
            f'{dash_attr} stroke-linejoin="round" marker-end="url(#{marker_id[color]})"/>'
        )
        sign = polarity.get(e.id)
        if sign in ("+", "-"):
            parts.append(
                f'<rect x="{lx - 8:.1f}" y="{ly - 9:.1f}" width="16" height="18" rx="4" '
                f'fill="{_CANVAS_BG}" stroke="{color}"/>'
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="central" '
                f'font-size="12" font-weight="700" fill="{color}">{sign}</text>'
            )
        parts.append("</g>")

    # Nodes.
    for e in entities:
        x, y, w, h = geom[e.id]
        color = _KIND_COLORS.get(e.kind, _KIND_FALLBACK_COLOR)
        badge = _KIND_LABELS.get(e.kind, "?")
        cy = y + h / 2
        parts.append(f'<g class="node" id="{escape(e.id, quote=True)}">')
        parts.append(
            f'<path d="{_rounded_rect_path(x, y, w, h, _NODE_RADIUS)}" '
            f'fill="{_CANVAS_BG}" stroke="{color}" stroke-width="2"/>'
        )
        parts.append(
            f'<rect x="{x + 10:.1f}" y="{cy - 8:.1f}" width="16" height="16" rx="4" fill="{color}"/>'
            f'<text x="{x + 18:.1f}" y="{cy:.1f}" text-anchor="middle" dominant-baseline="central" '
            f'font-size="10" font-weight="700" fill="#ffffff">{escape(badge)}</text>'
        )
        parts.append(
            f'<text x="{x + 34:.1f}" y="{cy:.1f}" dominant-baseline="central" '
            f'font-size="13" font-weight="500" fill="{_TEXT_PRIMARY}">{escape(_truncate(e.label, w))}</text>'
        )
        parts.append("</g>")

    parts.append("</svg>")
    return "".join(parts)
