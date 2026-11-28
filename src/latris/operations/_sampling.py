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
    correlations: dict[tuple[str, str], float] | None = None,
) -> list[dict[str, float]]:
    """``n`` joint draws. ``lhs`` stratifies each parameter into n bins. Parameters are independent unless
    ``correlations`` pairs some keys with a rank correlation, induced by :func:`induce_correlation`."""
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
    if correlations:
        columns = induce_correlation(columns, correlations, seed=seed)
    return [{k: columns[k][i] for k in keys} for i in range(n)]


def correlation_matrix(keys: list[str], correlations: dict[tuple[str, str], float]) -> Any:
    """The target rank-correlation matrix over ``keys``; ValueError if it isn't a possible one."""
    import numpy as np

    idx = {k: i for i, k in enumerate(keys)}
    c = np.eye(len(keys))
    for (a, b), rho in correlations.items():
        c[idx[a], idx[b]] = c[idx[b], idx[a]] = rho
    if float(np.min(np.linalg.eigvalsh(c))) <= 1e-9:
        raise ValueError("these correlations can't all hold at once (the matrix isn't positive definite): "
                         "e.g. A and B strongly positive, B and C strongly positive, but A and C negative")
    return c


def induce_correlation(columns: dict[str, list[float]], correlations: dict[tuple[str, str], float], *,
                       seed: int) -> dict[str, list[float]]:
    """Reorder each correlated column so the draws carry the target rank correlations (Iman & Conover 1982).

    Only the pairing of values across columns changes, so every parameter keeps exactly the values — and the
    Latin hypercube strata — it was drawn with. Van der Waerden scores, randomly permuted per column, are
    given the target correlation by Cholesky factors; each column then takes the ranks of its scores.
    """
    from statistics import NormalDist

    import numpy as np

    keys = sorted({k for pair in correlations for k in pair if k in columns})
    pairs = {p: r for p, r in correlations.items() if p[0] in columns and p[1] in columns}
    if len(keys) < 2 or not pairs:
        return columns
    n = len(columns[keys[0]])
    target = correlation_matrix(keys, pairs)
    rng = np.random.default_rng(seed + 104_729)
    scores = np.array([NormalDist().inv_cdf((i + 1) / (n + 1)) for i in range(n)])
    r = np.column_stack([rng.permutation(scores) for _ in keys])
    t = np.corrcoef(r, rowvar=False)
    q = np.linalg.cholesky(t)
    p = np.linalg.cholesky(target)
    s = r @ np.linalg.inv(q).T @ p.T
    out = dict(columns)
    for j, k in enumerate(keys):
        ordered = sorted(columns[k])
        rank = np.argsort(np.argsort(s[:, j], kind="stable"), kind="stable")
        out[k] = [ordered[i] for i in rank]
    return out


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


def dirichlet(rng: random.Random, probs: Sequence[float], n: float) -> list[float]:
    """One draw from Dirichlet(n · probs): a probability row "worth n observations" around ``probs``.

    Zero cells stay exactly zero (a structural impossibility isn't made possible by sampling).
    """
    draws = [rng.gammavariate(n * p, 1.0) if p > 0 else 0.0 for p in probs]
    total = sum(draws)
    if total <= 0:  # every positive alpha drew ~0 (tiny n): fall back to the point
        return list(probs)
    return [d / total for d in draws]


def beta_around(rng: random.Random, p: float, n: float) -> float:
    """One draw from Beta(n·p, n·(1−p)): a single probability worth n observations; 0 and 1 stay put."""
    if p <= 0 or p >= 1:
        return p
    return rng.betavariate(n * p, n * (1 - p))
