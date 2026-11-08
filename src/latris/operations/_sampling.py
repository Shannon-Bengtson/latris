"""Sampling for uncertainty analysis — quantiles, seeded Latin hypercube, percentiles.

Every draw goes through a distribution's inverse CDF (``ppf``), so the same
code serves random sampling, Latin hypercube sampling and the 5th/95th
percentile ranges a tornado uses. scipy's ``ppf`` is used when it is
installed (it's in the ``data`` extra); otherwise uniform, triangular, normal
and lognormal have exact pure-Python inverses and beta/gamma ask for scipy.

Reproducibility: one ``random.Random(seed)`` drives everything, in a fixed
order (parameters sorted by id), so a seed fully determines the samples.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from statistics import NormalDist
from typing import Any

from latris.schema.attributes import ParameterUncertainty

PERCENTILES: tuple[float, ...] = (0.0, 2.5, 12.5, 25.0, 50.0, 75.0, 87.5, 97.5, 100.0)


def _scipy_dist(spec: ParameterUncertainty) -> Any | None:
    try:
        from scipy import stats
    except ImportError:
        return None
    p = spec.params
    d = spec.distribution
    if d == "uniform":
        return stats.uniform(loc=p["min"], scale=p["max"] - p["min"])
    if d == "triangular":
        width = p["max"] - p["min"]
        return stats.triang(c=(p["mode"] - p["min"]) / width, loc=p["min"], scale=width)
    if d == "normal":
        return stats.norm(loc=p["mean"], scale=p["sd"])
    if d == "lognormal":
        mu, sigma = _lognormal_mu_sigma(p["mean"], p["sd"])
        return stats.lognorm(s=sigma, scale=math.exp(mu))
    if d == "beta":
        lo, hi = p.get("min", 0.0), p.get("max", 1.0)
        return stats.beta(p["alpha"], p["beta"], loc=lo, scale=hi - lo)
    if d == "gamma":
        return stats.gamma(p["shape"], scale=p["scale"])
    return None


def _lognormal_mu_sigma(mean: float, sd: float) -> tuple[float, float]:
    sigma2 = math.log(1.0 + (sd / mean) ** 2)
    return math.log(mean) - sigma2 / 2.0, math.sqrt(sigma2)


def _pure_ppf(spec: ParameterUncertainty, u: float) -> float:
    p = spec.params
    d = spec.distribution
    if d == "uniform":
        return p["min"] + u * (p["max"] - p["min"])
    if d == "triangular":
        a, c, b = p["min"], p["mode"], p["max"]
        f = (c - a) / (b - a) if b > a else 0.5
        if u < f:
            return a + math.sqrt(u * (b - a) * (c - a))
        return b - math.sqrt((1 - u) * (b - a) * (b - c))
    if d == "normal":
        return NormalDist(p["mean"], p["sd"]).inv_cdf(u)
    if d == "lognormal":
        mu, sigma = _lognormal_mu_sigma(p["mean"], p["sd"])
        return math.exp(NormalDist(mu, sigma).inv_cdf(u))
    raise RuntimeError(f"sampling a {d} distribution needs scipy; install it with: pip install 'latris[data]'")


def _pure_cdf(spec: ParameterUncertainty, x: float) -> float:
    p = spec.params
    if spec.distribution == "normal":
        return NormalDist(p["mean"], p["sd"]).cdf(x)
    if spec.distribution == "lognormal":
        if x <= 0:
            return 0.0
        mu, sigma = _lognormal_mu_sigma(p["mean"], p["sd"])
        return NormalDist(mu, sigma).cdf(math.log(x))
    return _ppf_inverse_bisect(spec, x)


def _ppf_inverse_bisect(spec: ParameterUncertainty, x: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _pure_ppf(spec, mid) < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


class Sampler:
    """Inverse-CDF access to one distribution, honouring optional min/max truncation."""

    def __init__(self, spec: ParameterUncertainty):
        if spec.distribution == "unknown":
            raise ValueError("the distribution is 'unknown'; set one before sampling")
        self.spec = spec
        self._dist = _scipy_dist(spec)
        truncates = spec.distribution in ("normal", "lognormal", "gamma")
        lo = spec.params.get("min") if truncates else None
        hi = spec.params.get("max") if truncates else None
        self._u_lo = self._cdf(lo) if lo is not None else 0.0
        self._u_hi = self._cdf(hi) if hi is not None else 1.0
        if self._u_hi - self._u_lo <= 1e-12:
            raise ValueError("the min/max truncation leaves no probability mass")

    def _cdf(self, x: float) -> float:
        if self._dist is not None:
            return float(self._dist.cdf(x))
        return _pure_cdf(self.spec, x)

    def ppf(self, u: float) -> float:
        u = min(max(u, 1e-12), 1 - 1e-12)
        q = self._u_lo + u * (self._u_hi - self._u_lo)
        if self._dist is not None:
            return float(self._dist.ppf(q))
        return _pure_ppf(self.spec, q)

    def quantile(self, q: float) -> float:
        return self.ppf(q)


def sample(
    specs: dict[str, ParameterUncertainty],
    n: int,
    *,
    seed: int,
    method: str = "lhs",
) -> list[dict[str, float]]:
    """``n`` joint draws (independent parameters). ``lhs`` stratifies each parameter into n bins."""
    if n < 1:
        raise ValueError("need at least one run")
    if method not in ("lhs", "random"):
        raise ValueError("sampling must be 'lhs' (Latin hypercube) or 'random'")
    rng = random.Random(seed)
    keys = sorted(specs)
    samplers = {k: Sampler(specs[k]) for k in keys}
    columns: dict[str, list[float]] = {}
    for k in keys:
        if method == "lhs":
            strata = list(range(n))
            rng.shuffle(strata)
            us = [(s + rng.random()) / n for s in strata]
        else:
            us = [rng.random() for _ in range(n)]
        columns[k] = [samplers[k].ppf(u) for u in us]
    return [{k: columns[k][i] for k in keys} for i in range(n)]


def percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile of already-sorted values (numpy's default method)."""
    if not sorted_values:
        return math.nan
    pos = (len(sorted_values) - 1) * pct / 100.0
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation (average ranks for ties); ``None`` if either side is constant."""
    if len(x) < 3 or len(x) != len(y):
        return None

    def ranks(v: Sequence[float]) -> list[float]:
        order = sorted(range(len(v)), key=v.__getitem__)
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)
