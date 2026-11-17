"""A model that is three model types at once — the shape of the 2026-11-17 reservoir-bloom agent retest.

One map holds a causal loop diagram (with a reinforcing loop), a two-stock system dynamics model
built *in place* on some of the loop map's factors, and a small Bayesian network beside them. Loop-map
links still point into the simulation (``Catchment load → Water-column phosphorus``,
``Bottom-water anoxia → Internal P release``): they belong to the loop map and must neither block a
run nor age its results.
"""

from __future__ import annotations

from pathlib import Path

CLD_LINKS = [  # (from, to, polarity)
    ("Climate warming", "Water temperature", "+"),
    ("Water temperature", "Thermal stratification", "+"),
    ("Thermal stratification", "Bottom-water anoxia", "+"),
    ("Bottom-water anoxia", "Internal P release", "+"),
    ("Internal P release", "Water-column phosphorus", "+"),
    ("Catchment load", "Water-column phosphorus", "+"),
    ("Water-column phosphorus", "Cyanobacteria biomass", "+"),
    ("Cyanobacteria biomass", "Bottom-water anoxia", "+"),  # closes the reinforcing loop
    ("Cyanobacteria biomass", "Treatment cost", "+"),
]

SD_ROLES = [
    ("Water-column phosphorus", "stock"), ("Sediment P pool", "stock"),
    ("External P load", "flow"), ("Settling", "flow"), ("Internal P release", "flow"),
    ("Catchment", "source_sink"),
    ("Catchment input", "constant"), ("Settling rate", "constant"), ("Release rate", "constant"),
]
SD_FLOW_EDGES = [
    ("Catchment", "External P load"), ("External P load", "Water-column phosphorus"),
    ("Water-column phosphorus", "Settling"), ("Settling", "Sediment P pool"),
    ("Sediment P pool", "Internal P release"), ("Internal P release", "Water-column phosphorus"),
]
SD_INFO_LINKS = [
    ("Catchment input", "External P load"), ("Settling rate", "Settling"), ("Release rate", "Internal P release"),
]

BN_LINKS = [("Hot week", "Bloom"), ("Bloom", "Customer exceedance"), ("Barrier fails", "Customer exceedance")]


def build_mixed_model(root: Path) -> Path:
    from latris.operations import bn as bn_ops
    from latris.operations import sd as sd_ops
    from latris.operations.edges import add_edge
    from latris.operations.findings import record_new_finding
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node
    from latris.operations.project import update_selected_models
    from latris.operations.view_attributes import set_view_attribute

    init_project(root, statement="What drives toxic blooms in the supply reservoir, and which option cuts the risk?")
    ids: dict[str, str] = {}

    def node(label: str) -> str:
        if label not in ids:
            ids[label] = add_node(label, kind="variable", root=root)[0].id
        return ids[label]

    for a, b, sign in CLD_LINKS:
        edge, _ = add_edge(node(a), node(b), kind="causal", root=root)
        set_view_attribute(edge.id, "cld", "polarity", sign, root=root)
    for a, b in SD_FLOW_EDGES:
        add_edge(node(a), node(b), kind="flow", root=root)
    for a, b in SD_INFO_LINKS:
        add_edge(node(a), node(b), kind="causal", root=root)
    for a, b in BN_LINKS:
        add_edge(node(a), node(b), kind="causal", root=root)

    update_selected_models(["cld", "sd", "bn"], root=root)

    for label, role in SD_ROLES:
        sd_ops.set_role(label, role, root=root)
    sd_ops.set_initial_value("Water-column phosphorus", 20, "kg", root=root)
    sd_ops.set_initial_value("Sediment P pool", 200, "kg", root=root)
    sd_ops.set_constant("Catchment input", 50, "kg/year", root=root)
    sd_ops.set_constant("Settling rate", 1.5, "1/year", root=root)
    sd_ops.set_constant("Release rate", 0.1, "1/year", root=root)
    sd_ops.set_equation("External P load", "catchment_input", "kg/year", root=root)
    sd_ops.set_equation("Settling", "water_column_phosphorus * settling_rate", "kg/year", root=root)
    sd_ops.set_equation("Internal P release", "sediment_p_pool * release_rate", "kg/year", root=root)

    for label in ("Hot week", "Bloom", "Customer exceedance", "Barrier fails"):
        bn_ops.set_state_space(label, ["yes", "no"], root=root)
    bn_ops.set_cpt("Hot week", [], [0.3, 0.7], root=root)
    bn_ops.set_cpt("Barrier fails", [], [0.05, 0.95], root=root)
    bn_ops.set_cpt("Bloom", ["Hot week"], [0.6, 0.4, 0.1, 0.9], root=root)
    bn_ops.set_cpt("Customer exceedance", ["Bloom", "Barrier fails"],
                   [0.5, 0.5, 0.05, 0.95, 0.02, 0.98, 0.0, 1.0], root=root)

    record_new_finding("Internal release and blooms reinforce each other (R1).", "structure", "cld",
                       target_ids=[ids["Bottom-water anoxia"]], root=root)
    record_new_finding("Phosphorus keeps rising for a decade without action.", "dynamics", "sd", root=root)
    record_new_finding("A failed barrier in a hot week drives exceedance risk.", "inference", "bn", root=root)
    return root
