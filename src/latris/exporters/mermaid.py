"""Mermaid diagram exporter — a plain-text sketch of the model for Markdown.

Embedded in the Markdown report as a ```mermaid block so the free output has
a picture wherever Mermaid renders (GitHub, most chat UIs, many editors).
Deliberately a rough sketch: labels and arrows only, edges labelled with CLD
polarity where known, otherwise with their kind.

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


def render(paths: ProjectPaths, *, model_type: str | None = None) -> str:
    """Return Mermaid ``flowchart`` source for the (optionally scoped) model.

    Returns an empty string when the model has no nodes, so callers can skip
    the section entirely.
    """
    substrate = load_model(Substrate, paths.conceptual_yaml)
    members = view_member_ids(paths, model_type)
    entities = [e for e in substrate.entities if members is None or e.id in members]
    if not entities:
        return ""
    node_ids = {e.id for e in entities}
    edges = [
        e for e in substrate.edges
        if (members is None or e.id in members) and e.from_id in node_ids and e.to_id in node_ids
    ]

    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()
    polarity = {e.target_id: e.value for e in pol_set.entries if e.attribute == "polarity"}

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
    return "\n".join(lines) + "\n"
