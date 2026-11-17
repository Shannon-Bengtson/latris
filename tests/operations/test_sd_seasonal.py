"""Seasonal functions: SIN, COS, MODULO and PI, on both the pint and the float path."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from latris.operations import sd as sd_ops
from latris.operations import sd_inference
from latris.operations._sd_eval import EquationError, parse
from tests.conftest import build_with_template_identity, clone_project


def _build(root: Path) -> Path:
    from latris.operations.edges import add_edge
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node

    init_project(root, statement="How does a seasonal inflow fill the tank?")
    ids = {}
    for label in ("Water", "Inflow", "Tap", "Amplitude", "Period", "Time of year"):
        ids[label] = add_node(label, root=root)[0].id
    for a, b, kind in [("Tap", "Inflow", "flow"), ("Inflow", "Water", "flow"), ("Amplitude", "Inflow", "causal"),
                       ("Period", "Inflow", "causal"), ("Period", "Time of year", "causal")]:
        add_edge(ids[a], ids[b], kind=kind, root=root)
    for label, role in [("Water", "stock"), ("Inflow", "flow"), ("Tap", "source_sink"), ("Amplitude", "constant"),
                        ("Period", "constant"), ("Time of year", "auxiliary")]:
        sd_ops.set_role(label, role, root=root)
    sd_ops.set_initial_value("Water", 0, "liter", root=root)
    sd_ops.set_constant("Amplitude", 10, "liter/year", root=root)
    sd_ops.set_constant("Period", 1, "year", root=root)
    sd_ops.set_equation("Inflow", "amplitude * (1 + SIN(2 * PI * TIME / period))", "liter/year", root=root)
    sd_ops.set_equation("Time of year", "MODULO(TIME, period)", "year", root=root)
    sd_ops.set_settings(dt=1 / 52, final_time=3, root=root)
    return root


@pytest.fixture(scope="module")
def _template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_with_template_identity(lambda: _build(tmp_path_factory.mktemp("tpl_seasonal") / "proj"))


@pytest.fixture
def seasonal_root(_template: Path, tmp_path: Path, git_identity) -> Path:
    return clone_project(_template, tmp_path / "proj")


def _analytic(t: float) -> float:
    # dW/dt = A (1 + sin(2πt)) → W(t) = A t + A/(2π) (1 − cos 2πt), A = 10
    return 10 * t + 10 / (2 * math.pi) * (1 - math.cos(2 * math.pi * t))


@pytest.mark.parametrize("fast", [True, False])
def test_seasonal_inflow_matches_the_analytic_solution(seasonal_root, fast):
    model = sd_ops.compile_project(root=seasonal_root)
    if fast:
        assert sd_inference.fast_model(model) is not None  # the float path compiles SIN / MODULO / PI
    result = sd_inference.simulate(model, fast=fast)
    water = next(i for i, label in result.labels.items() if label == "Water")
    for t, w in zip(result.times, result.series[water], strict=True):
        assert w == pytest.approx(_analytic(t), abs=1e-3)


def test_modulo_gives_the_time_within_each_period(seasonal_root):
    result = sd_ops.simulate(root=seasonal_root)
    season = next(i for i, label in result.labels.items() if label == "Time of year")
    for t, v in zip(result.times, result.series[season], strict=True):
        assert v == pytest.approx(t % 1.0, abs=1e-9) or v == pytest.approx(1.0, abs=1e-9)


def test_pi_is_not_a_variable_reference():
    assert parse("SIN(2 * PI * TIME)").names == frozenset()


def test_sin_of_a_dimensional_value_is_refused(seasonal_root):
    sd_ops.set_equation("Inflow", "amplitude * (1 + SIN(period))", "liter/year", root=seasonal_root)
    with pytest.raises(EquationError, match="dimensionless"):
        sd_ops.simulate(root=seasonal_root)
