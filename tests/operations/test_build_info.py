"""``build`` tells the author what applying a formalism's values means (``info``), apart from failures."""

from __future__ import annotations

from latris.operations.build import build_from_spec, load_spec
from latris.operations.init import init_project


def test_sd_equations_say_what_they_read(tmp_path, git_identity):
    root = tmp_path / "m"
    init_project(root, statement="How full does the bathtub get?")
    result = build_from_spec(load_spec("""
factors: [{label: Water}, {label: Outflow}, {label: Drain Rate}, {label: Drain}]
links:
  - {from: Water, to: Outflow, kind: flow}
  - {from: Outflow, to: Drain, kind: flow}
  - {from: Drain Rate, to: Outflow}
sd:
  roles: [{node: Water, role: stock}, {node: Outflow, role: flow}, {node: Drain Rate, role: constant},
          {node: Drain, role: source_sink}]
  equations: [{node: Outflow, expression: water * drain_rate, units: liter/year}]
"""), root=root)
    assert result.info == ["Outflow reads: drain_rate = Drain Rate, water = Water"]
    assert not result.notes  # information, not a failure
