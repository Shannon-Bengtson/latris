"""Graphviz DOT exporter — static graph rendering for reports/diagrams.

Not for live UI. Users pipe the output to ``dot -Tpng`` (or similar) to
produce an image.

Views:
- system_map : plain directed graph; edge labels = kind (full substrate).
- cld        : edges labeled with polarity (+/-) where known.
- dag        : same substrate, styled for a DAG layout (top-to-bottom).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from latris.exporters._scope import view_member_ids
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import PolaritySet, Substrate

ViewKind = Literal["system_map", "cld", "dag"]


def _dot_escape(text: str) -> str:
    """Escape characters that break DOT string literals."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render(paths: ProjectPaths, view: ViewKind = "system_map") -> str:
    substrate = load_model(Substrate, paths.conceptual_yaml)
    pol_path = paths.view_attribute_path("cld", "polarity")
    pol_set = load_model(PolaritySet, pol_path) if pol_path.exists() else PolaritySet()
    polarity = {(e.target_id, e.attribute): e for e in pol_set.entries}

    # Filter by mappings if any exist for this view.
    mapped_ids = view_member_ids(paths, view)
    if mapped_ids is not None:
        entities = [e for e in substrate.entities if e.id in mapped_ids]
        edges = [e for e in substrate.edges if e.id in mapped_ids]
    else:
        entities = list(substrate.entities)
        edges = list(substrate.edges)

    graph_name = _dot_escape(paths.root.name)
    rankdir = "TB" if view == "dag" else "LR"

    lines: list[str] = [
        f'digraph "{graph_name}" {{',
        f"  rankdir={rankdir};",
        '  node [shape=box, style="rounded,filled", fillcolor="#f5f5f5", fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=10];',
        "",
    ]

    if not entities and not edges:
        lines.append("  // empty project")
        lines.append("}")
        return "\n".join(lines) + "\n"

    # Nodes
    for n in entities:
        label = f"{_dot_escape(n.label)}\\n[{n.kind}]"
        # Emit the schema node ID so the rendered SVG carries an addressable
        # <g class="node" id="..."> for Story emphasis highlighting.
        lines.append(f'  "{n.id}" [label="{label}", id="{_dot_escape(n.id)}"];')
    if entities:
        lines.append("")

    # Edges
    for e in edges:
        if view == "cld":
            pol = polarity.get((e.id, "polarity"))
            edge_label = pol.value if pol else ""
            attrs = f'label="{_dot_escape(edge_label)}"' if edge_label else ""
        else:
            attrs = f'label="{e.kind}"'
        # Always emit the schema edge ID so the rendered SVG carries an
        # addressable <g class="edge" id="..."> for Story emphasis.
        id_attr = f'id="{_dot_escape(e.id)}"'
        combined = f"{attrs}, {id_attr}" if attrs else id_attr
        line = f'  "{e.from_id}" -> "{e.to_id}" [{combined}];'
        lines.append(line)

    lines.append("}")
    return "\n".join(lines) + "\n"


def write(paths: ProjectPaths, target: Path, *, view: ViewKind = "system_map") -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(paths, view=view), encoding="utf-8", newline="")
    return target
