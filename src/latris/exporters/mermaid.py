"""Mermaid diagram exporter — a plain-text sketch of the model for Markdown.

Embedded in the Markdown report as a ```mermaid block so the free output has
a picture wherever Mermaid renders (GitHub, most chat UIs, many editors).
Deliberately a rough sketch: labels and arrows, edges labelled (and
coloured) with CLD polarity where known, otherwise labelled with their kind.
Mermaid can't label loops, so :func:`loop_legend` lists them for the text
under the diagram.

Mermaid node ids are positional (``n0``, ``n1``, ...) rather than schema ids,
so the source stays short and never trips Mermaid's id grammar.
"""

from __future__ import annotations

from latris.exporters._scope import view_member_ids
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import PolaritySet, Substrate

# Edge kinds that carry mechanism draw solid; everything else (policy,
# identity, association, ...) draws dotted. Mirrors markdown._CAUSAL_EDGE_KINDS.
_SOLID_EDGE_KINDS = frozenset({"causal", "temporal", "decomposition", "conditional", "flow"})

# Link colours by polarity — mid-tone so they read on light and dark themes.
_POLARITY_STROKE = {"+": "#2e8b57", "-": "#c0392b"}


def _mermaid_text(text: str) -> str:
    """Make text safe inside a double-quoted Mermaid label."""
    return (
        text.replace("\r", " ")
        .replace("\n", " ")
        .replace("#", "#35;")
        .replace('"', "#quot;")
        .replace("<", "#lt;")
        .replace(">", "#gt;")
    )


def _scoped(paths: ProjectPaths, model_type: str | None):
    substrate = load_model(Substrate, paths.conceptual_yaml)
    members = view_member_ids(paths, model_type)
    entities = [e for e in substrate.entities if members is None or e.id in members]
    node_ids = {e.id for e in entities}
    edges = [
        e for e in substrate.edges
        if (members is None or e.id in members) and e.from_id in node_ids and e.to_id in node_ids
    ]
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()
    polarity = {e.target_id: e.value for e in pol_set.entries if e.attribute == "polarity"}
    return entities, edges, polarity


def render(paths: ProjectPaths, *, model_type: str | None = None) -> str:
    """Return Mermaid ``flowchart`` source for the (optionally scoped) model.

    Returns an empty string when the model has no nodes, so callers can skip
    the section entirely.
    """
    entities, edges, polarity = _scoped(paths, model_type)
    if not entities:
        return ""

    direction = "TB" if model_type == "dag" else "LR"
    alias = {e.id: f"n{i}" for i, e in enumerate(entities)}
    lines = [f"flowchart {direction}"]
    for e in entities:
        lines.append(f'    {alias[e.id]}["{_mermaid_text(e.label)}"]')
    for e in edges:
        label = polarity.get(e.id) or ("" if e.kind == "causal" else e.kind)
        arrow = "-->" if e.kind in _SOLID_EDGE_KINDS else "-.->"
        if label:
            lines.append(f'    {alias[e.from_id]} {arrow}|"{_mermaid_text(label)}"| {alias[e.to_id]}')
        else:
            lines.append(f"    {alias[e.from_id]} {arrow} {alias[e.to_id]}")
    # linkStyle indexes links in the order they were written.
    for sign, stroke in _POLARITY_STROKE.items():
        idx = [str(i) for i, e in enumerate(edges) if polarity.get(e.id) == sign]
        if idx:
            lines.append(f"    linkStyle {','.join(idx)} stroke:{stroke},stroke-width:2px")
    return "\n".join(lines) + "\n"


def loop_legend(paths: ProjectPaths, *, model_type: str | None = None) -> list[str]:
    """Feedback loops as ``R1: A → B → A`` lines, one per mechanism.

    Cycles that differ by one alternative step are one mechanism (see
    ``graph_analysis.group_loop_mechanisms``); the extra routes are noted.
    Empty when the model has no classified loops.
    """
    from latris.operations.feedback import feedback_edges, link_polarity
    from latris.operations.graph_analysis import (
        classify_loop,
        find_all_loops,
        group_loop_mechanisms,
    )

    entities, edges, polarity = _scoped(paths, model_type)
    labels = {e.id: e.label for e in entities}
    polarity = {**link_polarity(edges, paths), **polarity}
    loops = [classify_loop(loop, polarity) for loop in find_all_loops(feedback_edges(edges, paths))]
    counters = {"R": 0, "B": 0}
    out = []
    for group in group_loop_mechanisms([loop for loop in loops if loop.classification in counters]):
        cls = group[0].classification
        counters[cls] += 1
        shortest = min(group, key=lambda loop: len(loop.node_ids))
        path = " → ".join(labels.get(n, n) for n in (*shortest.node_ids, shortest.node_ids[0]))
        word = "reinforcing" if cls == "R" else "balancing"
        extra = f" (+{len(group) - 1} alternative route{'s' if len(group) > 2 else ''})" if len(group) > 1 else ""
        out.append(f"**{cls}{counters[cls]}** ({word}): {path}{extra}")
    return out
