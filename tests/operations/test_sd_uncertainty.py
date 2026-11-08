"""Uncertainty ranges, sampling, Monte Carlo bands and one-at-a-time sensitivity.

Numerical checks use the bathtub's closed form: W(t) = I/k + (W0 − I/k)·e^(−k·t).
"""

from __future__ import annotations

import math

import pytest

from latris.operations import _sampling, uncertainty
from latris.operations import analysis_results as ar
from latris.operations import sd as sd_ops
from latris.schema.attributes import ParameterUncertainty

pytest.importorskip("scipy")

SETTINGS = {"final_time": 10, "dt": 0.25, "saveper": 1, "method": "adaptive"}


def _exact(t, inflow=5.0, k=0.1, initial=100.0):
    eq = inflow / k
    return eq + (initial - eq) * math.exp(-k * t)


def _spec(distribution, **params):
    return ParameterUncertainty(target_id="x", distribution=distribution, params=params)


# ── schema + sampling ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("distribution", "params", "match"),
    [
        ("triangular", {"min": 1, "max": 3}, "missing mode"),
        ("uniform", {"min": 3, "max": 1}, "min must be less"),
        ("normal", {"mean": 1, "sd": -1}, "sd must be positive"),
        ("lognormal", {"mean": -1, "sd": 1}, "positive mean"),
        ("gamma", {"shape": 1, "scale": 1, "mode": 2}, "unexpected mode"),
    ],
)
def test_distribution_parameters_are_validated(distribution, params, match):
    with pytest.raises(ValueError, match=match):
        _spec(distribution, **params)


def test_latin_hypercube_hits_every_stratum_once():
    n = 50
    draws = _sampling.sample({"x": _spec("uniform", min=0, max=1)}, n, seed=7)
    bins = sorted(int(d["x"] * n) for d in draws)
    assert bins == list(range(n))


def test_seed_determines_samples():
    specs = {"a": _spec("normal", mean=0, sd=1), "b": _spec("triangular", min=0, mode=1, max=4)}
    assert _sampling.sample(specs, 20, seed=3) == _sampling.sample(specs, 20, seed=3)
    assert _sampling.sample(specs, 20, seed=3) != _sampling.sample(specs, 20, seed=4)


def test_truncation_keeps_draws_in_bounds():
    draws = _sampling.sample({"x": _spec("normal", mean=0, sd=1, min=-0.5, max=2)}, 500, seed=1, method="random")
    assert all(-0.5 <= d["x"] <= 2 for d in draws)


@pytest.mark.parametrize(
    "spec",
    [_spec("uniform", min=2, max=5), _spec("triangular", min=0, mode=1, max=4),
     _spec("normal", mean=3, sd=2), _spec("lognormal", mean=2, sd=0.5), _spec("normal", mean=0, sd=1, min=-1)],
)
def test_pure_python_inverse_matches_scipy(spec, monkeypatch):
    with_scipy = _sampling.Sampler(spec)
    monkeypatch.setattr(_sampling, "_scipy_dist", lambda _spec: None)
    pure = _sampling.Sampler(spec)
    for u in (0.01, 0.05, 0.3, 0.5, 0.77, 0.95, 0.99):
        assert pure.ppf(u) == pytest.approx(with_scipy.ppf(u), rel=1e-6, abs=1e-9)


def test_percentile_and_spearman():
    assert _sampling.percentile([1, 2, 3, 4], 50) == 2.5
    assert _sampling.percentile([1, 2, 3, 4], 0) == 1 and _sampling.percentile([1, 2, 3, 4], 100) == 4
    assert _sampling.spearman([1, 2, 3, 4], [10, 20, 30, 45]) == pytest.approx(1.0)
    assert _sampling.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert _sampling.spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None


# ── store ────────────────────────────────────────────────────────────


def test_set_uncertainty_checks_target_and_value(sd_bathtub_root):
    root = sd_bathtub_root
    with pytest.raises(ValueError, match="lies outside"):
        uncertainty.set_uncertainty("Drain Rate", "uniform", {"min": 0.5, "max": 1}, root=root)
    with pytest.raises(ValueError):
        uncertainty.set_uncertainty("Inflow", "uniform", {"min": 1, "max": 9}, root=root)  # a flow
    entry, _ = uncertainty.set_uncertainty(
        "Drain Rate", "uniform", {"min": 0.05, "max": 0.2}, reason="plumber's estimate", origin="ai-proposed",
        root=root,
    )
    assert entry.parameter_cell_id == "sd:constant" and entry.origin == "ai-proposed"
    uncertainty.set_uncertainty("Water", "triangular", {"min": 80, "mode": 100, "max": 110}, root=root)
    assert set(uncertainty.sd_specs(sd_ops.require_project(root))) == {
        e.target_id for e in uncertainty.list_uncertainty(root=root)
    }
    uncertainty.clear_uncertainty("Water", root=root)
    assert len(uncertainty.list_uncertainty(root=root)) == 1


# ── Monte Carlo ──────────────────────────────────────────────────────


def test_monte_carlo_bands_match_closed_form(sd_bathtub_root):
    root = sd_bathtub_root
    with pytest.raises(ValueError, match="no uncertain values"):
        sd_ops.run_monte_carlo(runs=10, settings=SETTINGS, root=root)
    uncertainty.set_uncertainty("Drain Rate", "uniform", {"min": 0.05, "max": 0.2}, root=root)
    payload = sd_ops.run_monte_carlo(runs=200, seed=11, settings=SETTINGS, root=root)
    water = payload["variables"][0]
    assert payload["labels"][water] == "Water" and payload["succeeded"] == 200
    # W(10) falls monotonically as k rises, so its median is W at the median k (0.125).
    assert payload["end"][water]["p50"] == pytest.approx(_exact(10, k=0.125), rel=5e-3)
    assert payload["end"][water]["p0"] >= _exact(10, k=0.2) - 1e-6
    assert payload["end"][water]["p100"] <= _exact(10, k=0.05) + 1e-6
    assert payload["end"][water]["baseline"] == pytest.approx(_exact(10), rel=1e-5)
    for t in range(len(payload["times"])):
        column = [payload["bands"][water]["series"][f"{p:g}"][t] for p in _sampling.PERCENTILES]
        assert column == sorted(column)
    assert payload["influence"][water][0]["rho"] == pytest.approx(-1.0)

    again = sd_ops.run_monte_carlo(runs=200, seed=11, settings=SETTINGS, root=root)
    assert again["end"] == payload["end"]


def test_monte_carlo_is_recorded_and_goes_stale_with_its_ranges(sd_bathtub_root):
    root = sd_bathtub_root
    uncertainty.set_uncertainty("Drain Rate", "uniform", {"min": 0.05, "max": 0.2}, root=root)
    payload = sd_ops.run_monte_carlo(runs=20, settings=SETTINGS, root=root)
    _, run_id = sd_ops.record_monte_carlo(payload, root=root)
    shown = ar.report_results(root=root)
    assert [r.run.id for r in shown] == [run_id] and not shown[0].stale
    assert shown[0].run.seed == 1234
    uncertainty.set_uncertainty("Drain Rate", "uniform", {"min": 0.05, "max": 0.3}, root=root)
    assert ar.report_results(root=root)[0].stale


def test_monte_carlo_time_guard(sd_bathtub_root):
    uncertainty.set_uncertainty("Drain Rate", "uniform", {"min": 0.05, "max": 0.2}, root=sd_bathtub_root)
    with pytest.raises(ValueError, match="would take about"):
        sd_ops.run_monte_carlo(runs=1000, max_seconds=0.0001, settings=SETTINGS, root=sd_bathtub_root)


# ── one-at-a-time sensitivity ────────────────────────────────────────


def test_tornado_ranks_by_swing_with_closed_form_values(sd_bathtub_root):
    root = sd_bathtub_root
    uncertainty.set_uncertainty("Drain Rate", "uniform", {"min": 0.05, "max": 0.2}, root=root)
    payload = sd_ops.run_sensitivity("Water", metric="final", settings=SETTINGS, root=root)
    rows = {r["label"]: r for r in payload["parameters"]}
    assert [r["label"] for r in payload["parameters"]][0] == "Drain Rate"

    drain = rows["Drain Rate"]
    assert drain["range_source"].startswith("uniform")
    assert drain["low"] == pytest.approx(0.0575) and drain["high"] == pytest.approx(0.1925)
    assert drain["result_low"] == pytest.approx(_exact(10, k=0.0575), rel=1e-4)
    assert drain["result_high"] == pytest.approx(_exact(10, k=0.1925), rel=1e-4)

    inflow = rows["Inflow Rate"]
    assert inflow["range_source"] == "±10%"
    assert inflow["swing"] == pytest.approx(_exact(10, inflow=5.5) - _exact(10, inflow=4.5), rel=1e-4)
    assert all(r["weak"] for r in payload["parameters"])  # nothing is human-verified in the fixture
    assert payload["baseline"] == pytest.approx(_exact(10), rel=1e-5)


def test_tornado_metrics(sd_bathtub_root):
    root = sd_bathtub_root
    peak_time = sd_ops.run_sensitivity("Water", metric="peak-time", settings=SETTINGS, root=root)
    assert peak_time["baseline"] == 0 and peak_time["units"] == "years"  # draining from 100 L: peak at t=0
    at5 = sd_ops.run_sensitivity("Water", metric="at:5", settings=SETTINGS, root=root)
    assert at5["baseline"] == pytest.approx(_exact(5), rel=1e-4)
    with pytest.raises(ValueError, match="outside the simulated time"):
        sd_ops.run_sensitivity("Water", metric="at:50", settings=SETTINGS, root=root)
    with pytest.raises(ValueError, match="unknown metric"):
        sd_ops.run_sensitivity("Water", metric="median", settings=SETTINGS, root=root)
