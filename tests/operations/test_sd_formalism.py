"""SD as a registered formalism (latris#3): outcome kept with its settings, its diagram, its spec block."""

from __future__ import annotations

from latris.exporters.mermaid import render as mermaid
from latris.operations import formalisms
from latris.operations import sd as sd_ops
from latris.operations.view_roles import set_role
from latris.repo.layout import ProjectPaths


def test_sd_is_registered_with_its_cli_and_routes():
    f = formalisms.get("sd")
    assert f is not None and f.spec_field == "sd"
    assert f.cli == ("latris.cli.sd_cmd", "sd") and f.routes == "latris.server.routes.sd"


def test_outcome_is_kept_with_the_settings(sd_bathtub_root):
    root = sd_bathtub_root
    target_id, _ = set_role("Water", "sd", "outcome", root=root)  # `latris view role sd Water outcome`
    assert sd_ops.get_settings(root=root).outcome == target_id
    assert formalisms.get("sd").outcome_ids(ProjectPaths(root)) == {target_id}


def test_diagram_draws_stocks_flows_and_clouds(sd_bathtub_root):
    src = mermaid(ProjectPaths(sd_bathtub_root), model_type="sd")
    assert '["Water"]' in src  # stock: a box
    assert '{{"Inflow"}}' in src  # flow: a hexagon
    assert '(("Tap"))' in src  # source: a circle
    assert "==>" in src  # flows are thick


def test_structure_problems_are_the_sd_check_gaps(sd_diagram_root):
    assert formalisms.get("sd").structure_problems(sd_diagram_root)  # roles missing


def test_a_complete_model_has_no_structure_problems(sd_bathtub_root):
    assert formalisms.get("sd").structure_problems(sd_bathtub_root) == []


def test_spec_block_round_trips(sd_bathtub_root):
    from latris.operations.share_link import export_spec

    _, spec = export_spec(root=sd_bathtub_root, model_type="sd")
    assert spec.sd is not None and {r.role for r in spec.sd.roles} >= {"stock", "flow", "constant"}
    known = {e for e in ("Water", "Inflow", "Outflow", "Inflow Rate", "Drain Rate", "Tap", "Drain")}
    assert formalisms.get("sd").spec_check(spec.sd, lambda n: n in known, None) == []
    assert formalisms.get("sd").spec_check(spec.sd, lambda n: False, None)  # every name unknown
