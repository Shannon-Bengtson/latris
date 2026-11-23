"""Global sensitivity analysis — which uncertain inputs the result's uncertainty comes from, all at once.

A Monte Carlo's rank correlations say which input moves with the result; a
tornado moves one input at a time with the rest held still. Neither sees
inputs that matter only together, or effects that aren't monotone. Global
sensitivity analysis varies every uncertain input over its whole range
together and apportions the result's variance among them (Saltelli et al.
2008, *Global Sensitivity Analysis: The Primer*):

- **Sobol indices** (Sobol 2001). The first-order index S1 of an input is the
  share of the result's variance it explains on its own; the total index ST
  adds every interaction it takes part in. ST near 0: the input could be
  fixed anywhere in its range without changing the result's spread. ST well
  above S1: it matters through interactions. Estimated on a scrambled Sobol
  sequence with Saltelli's (2010) first-order and Jansen's (1999) total
  estimators, n·(k + 2) model runs for k inputs, with bootstrap 95%
  intervals.
- **Morris elementary effects** (Morris 1991; Campolongo, Cariboni & Saltelli
  2007), a cheaper screen: r one-at-a-time trajectories through the inputs'
  quantiles, r·(k + 1) runs. μ* (the mean absolute effect) ranks importance;
  σ (their spread) flags interaction or non-linearity.

Inputs are the ranges already given for Monte Carlo or PSA — the same
distributions, with their provenance — sampled on the unit hypercube and
mapped through each distribution's quantile function, so the indices refer
to those distributions. Each model type supplies its inputs and a function
from them to named outputs (``_PROVIDERS``): the risk types, decision trees,
Markov models, system dynamics and Bayesian networks. Inputs are independent
(as the indices require). A set of probabilities — a chance node's branches,
a state's transitions out, a Bayesian-network table worth n observations —
is one input made of several columns (a group: Jacques, Lavergne & Devictor
2006), decoded into an exact Dirichlet draw; its index is the whole set's.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations import _sampling as smp
from latris.repo.project import require_project
from latris.schema.attributes import ParameterUncertainty

METHODS = ("sobol", "morris")
KINDS = {"fault_tree": "ft-gsa", "bow_tie": "bt-gsa", "event_tree": "et-gsa", "decision_tree": "dt-gsa",
         "markov": "markov-gsa", "sd": "sd-gsa", "bn": "bn-gsa"}
MAX_RUNS = 200_000
BOOTSTRAP = 200
MORRIS_LEVELS = 4
MORRIS_TAIL = 0.025


@dataclass
class Problem:
    """What a model type gives the analysis: its uncertain inputs and a function from them to named outputs."""

    keys: list[str]  # input keys, in a fixed order
    labels: dict[str, str]
    specs: dict[str, ParameterUncertainty]
    points: dict[str, float | None]
    evaluate: Callable[[dict[str, float]], dict[str, float]]  # values by key → outputs by name
    primary: str
    fixed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    units: str | None = None
    # Inputs that are sets of probabilities: key → the Dirichlet parameters of each of its parts (a chance
    # node's branches, a state's transitions out, each row of a Bayesian-network table). Such an input is
    # one group of columns, decoded through gamma quantiles; ``evaluate`` gets its parts' probabilities.
    groups: dict[str, list[list[float]]] = field(default_factory=dict)

    def point_values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in self.keys:
            if k in self.groups:
                out[k] = [[a / sum(alpha) for a in alpha] for alpha in self.groups[k]]
            else:
                out[k] = self.points[k]
        return out

    def widths(self) -> list[int]:
        return [sum(len(a) for a in self.groups[k]) if k in self.groups else 1 for k in self.keys]


# ── estimators (pure numpy) ─────────────────────────────────────────


def _unit_samples(k: int, n: int, seed: int):
    """(A, B): two n × k matrices on the unit hypercube from one scrambled Sobol sequence of dimension 2k."""
    import numpy as np
    from scipy.stats import qmc

    m = max(1, math.ceil(math.log2(n)))
    s = qmc.Sobol(d=2 * k, scramble=True, seed=seed).random_base2(m)[:n]
    s = np.clip(s, 1e-9, 1 - 1e-9)
    return s[:, :k], s[:, k:]


def _columns(k: int, widths: list[int] | None) -> list[list[int]]:
    """Each input's columns: one apiece, or ``widths[i]`` for an input that is a group of columns."""
    widths = widths or [1] * k
    out, c = [], 0
    for w in widths:
        out.append(list(range(c, c + w)))
        c += w
    return out


def sobol_indices(f: Callable[[Any], Any], k: int, n: int, seed: int,
                  widths: list[int] | None = None) -> dict[str, Any]:
    """Sobol S1 and ST of ``f`` (rows of unit-hypercube points → an array of outputs, one column each).

    Saltelli (2010) S1 = mean(f(B)·(f(AB_i) − f(A))) / V; Jansen (1999) ST = mean((f(A) − f(AB_i))²) / 2V,
    with V the variance of f over A and B; bootstrap 95% intervals. With ``widths``, input i spans that many
    columns, all swapped together (group indices; Jacques, Lavergne & Devictor 2006).
    """
    import numpy as np

    cols = _columns(k, widths)
    a, b = _unit_samples(sum(len(c) for c in cols), n, seed)
    ya, yb = f(a), f(b)
    yab = []
    for i in range(k):
        ab = a.copy()
        ab[:, cols[i]] = b[:, cols[i]]
        yab.append(f(ab))
    yab_arr = np.stack(yab)  # k × n × outputs
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(BOOTSTRAP, n))

    def est(ia):
        a_, b_, ab_ = ya[ia], yb[ia], yab_arr[:, ia]
        v = np.var(np.concatenate([a_, b_], axis=-2), axis=-2)
        v = np.where(v > 0, v, np.nan)
        s1 = np.mean(b_ * (ab_ - a_), axis=-2) / v
        st = 0.5 * np.mean((a_ - ab_) ** 2, axis=-2) / v
        return s1, st, v

    all_rows = np.arange(n)
    s1, st, _ = est(all_rows)
    boot_s1, boot_st = [], []
    for ia in idx:
        b1, bt, _ = est(ia)
        boot_s1.append(b1)
        boot_st.append(bt)
    q = lambda arr: 1.96 * np.nanstd(np.stack(arr), axis=0)  # noqa: E731
    return {"S1": s1, "ST": st, "S1_conf": q(boot_s1), "ST_conf": q(boot_st),
            "variance": np.var(np.concatenate([ya, yb]), axis=0),
            "mean": np.mean(np.concatenate([ya, yb]), axis=0), "runs": n * (k + 2)}


def morris_effects(f: Callable[[Any], Any], k: int, r: int, seed: int,
                   levels: int = MORRIS_LEVELS, widths: list[int] | None = None) -> dict[str, Any]:
    """Morris elementary effects over ``r`` trajectories on a ``levels``-level grid of quantiles.

    Each step moves one input by the standard Δ = p / 2(p − 1) of its grid; the effect is the output's change
    per unit of quantile. μ* = mean |EE|, σ = sd of EE, with bootstrap 95% on μ*. With ``widths``, an input
    spanning several columns moves them all in one step (groups; Campolongo, Cariboni & Saltelli 2007) — its
    μ* is then the one to read, as μ and σ mix the directions its columns moved in.
    """
    import numpy as np

    if levels < 2 or levels % 2:
        raise ValueError("Morris needs an even number of levels")
    rng = np.random.default_rng(seed)
    # The standard grid k/(p − 1) and step Δ = p / 2(p − 1), over the central 95% of each distribution (the
    # quantile function is unbounded at 0 and 1 for most families).
    grid = MORRIS_TAIL + (1 - 2 * MORRIS_TAIL) * np.arange(levels) / (levels - 1)
    jump = levels // 2
    delta = (1 - 2 * MORRIS_TAIL) * jump / (levels - 1)
    cols = _columns(k, widths)
    width = sum(len(c) for c in cols)
    points, moved, signs = [], [], []
    for _ in range(r):
        x = rng.integers(0, levels, size=width)
        order = rng.permutation(k)
        traj = [grid[x].copy()]
        for i in order:
            ups = [x[c] + jump < levels for c in cols[i]]
            for c, up in zip(cols[i], ups, strict=True):
                x[c] = x[c] + jump if up else x[c] - jump
            traj.append(grid[x].copy())
            moved.append(i)
            signs.append(1.0 if sum(ups) * 2 >= len(ups) else -1.0)
        points.append(np.array(traj))
    y = f(np.concatenate(points))  # (r·(k+1)) × outputs
    y = y.reshape(r, k + 1, -1)
    ee = np.zeros((r, k, y.shape[-1]))
    step = 0
    for t in range(r):
        for j in range(k):
            i = moved[step]
            ee[t, i] = (y[t, j + 1] - y[t, j]) * signs[step] / delta
            step += 1
    mu_star = np.mean(np.abs(ee), axis=0)
    boot = [np.mean(np.abs(ee[rng.integers(0, r, size=r)]), axis=0) for _ in range(BOOTSTRAP)]
    return {"mu_star": mu_star, "mu": np.mean(ee, axis=0), "sigma": np.std(ee, axis=0, ddof=1) if r > 1
            else np.zeros_like(mu_star), "mu_star_conf": 1.96 * np.std(np.stack(boot), axis=0),
            "runs": r * (k + 1)}


# ── each model type's inputs and outputs ────────────────────────────


def _risk(model_type: str, paths, _opts) -> Problem:
    from latris.operations import risk_uncertainty as ru

    model = ru._BUILD[model_type](paths)
    ranges = {k: v for k, v in ru.specs(model_type, paths).items() if k in model.inputs}
    keys = sorted(ranges, key=lambda k: model.labels[k])

    def evaluate(x: dict[str, float]) -> dict[str, float]:
        vals = {k: min(max(v, 0.0), 1.0) if ru._is_probability(k) else max(v, 0.0) for k, v in x.items()}
        return model.evaluate({**model.inputs, **vals})

    fixed = sorted(model.labels[k] for k in model.inputs if k not in ranges)
    return Problem(keys, {k: model.labels[k] for k in keys}, ranges, {k: model.inputs[k] for k in keys}, evaluate,
                   model.primary, fixed, units=model.quantity)


def _ignored(model_type: str, paths, labels: dict[str, str]) -> list[str]:
    """Correlations set between ranges, which this analysis can't honour (the indices need independence)."""
    from latris.operations import psa

    rows = psa._correlation_rows(model_type, paths, labels)
    if not rows:
        return []
    pairs = ", ".join(f"{c['a']} with {c['b']}" for c in rows)
    return [f"Inputs vary independently here, so the correlation of {pairs} is ignored (Sobol and Morris need "
            "independent inputs; the PSA honours it)"]


def _set_groups(sets: dict[str, tuple[ParameterUncertainty, list[float]]]) -> dict[str, list[list[float]]]:
    """A PSA Dirichlet range (one set of probabilities, worth n observations) as a one-part group."""
    return {k: [[e.params["n"] * p for p in probs]] for k, (e, probs) in sets.items()}


def _first_parts(x: dict[str, Any], sets) -> dict[str, Any]:
    """The PSA's ``apply`` takes a set's probabilities as one vector: a one-part group's only part."""
    return {k: (v[0] if k in sets else v) for k, v in x.items()}


def _dt(paths, _opts) -> Problem:
    from latris.operations import decision_tree as dt
    from latris.operations import psa

    t = dt.load_tree(root=paths.root)
    if t.problems:
        raise ValueError("the decision tree is incomplete; `latris dt check` lists what's missing")
    scalar, sets, labels, points, apply = psa._dt_inputs(t, psa.ranges("decision_tree", paths))
    point = psa._dt_options(t, dt.rollback(t)[0])
    order = sorted(point, key=lambda o: (-t.sign * point[o], list(point).index(o)))
    gap = f"advantage of {order[0]} over {order[1]}" if len(order) > 1 else None

    def evaluate(x: dict[str, Any]) -> dict[str, float]:
        opts = psa._dt_options(t, dt.rollback(apply(_first_parts(x, sets)))[0])
        out = {f"{o} (expected value)": v for o, v in opts.items()}
        if gap:
            out[gap] = t.sign * (opts[order[0]] - opts[order[1]])
        return out

    keys = sorted([*scalar, *sets], key=lambda k: labels[k])
    return Problem(keys, {k: labels[k] for k in keys}, {**scalar, **{k: e for k, (e, _) in sets.items()}},
                   {k: points[k] for k in keys}, evaluate, gap or f"{order[0]} (expected value)",
                   psa._dt_fixed(t, set(scalar)), _ignored("decision_tree", paths, labels), units=t.settings.units,
                   groups=_set_groups(sets))


def _markov(paths, _opts) -> Problem:
    from latris.operations import markov, psa

    m = markov.load(root=paths.root)
    if m.problems:
        raise ValueError("the Markov model is incomplete; `latris markov check` lists what's missing")
    scalar, sets, labels, points, _leaving, apply = psa._mk_inputs(m, psa.ranges("markov", paths))
    s = m.settings
    strategies = m.strategy_names()
    names = [m.labels[x] if x else markov.BASE_CASE for x in strategies]
    ou = s.outcome_units or "outcome"
    point = {n: markov.totals(m, x)[:2] for n, x in zip(names, strategies, strict=True)}
    pair = None
    if len(names) > 1 and s.wtp is not None:
        nmb = {n: s.wtp * o - c for n, (c, o) in point.items()}
        a, b = sorted(nmb, key=lambda n: -nmb[n])[:2]
        pair = (a, b, f"net monetary benefit of {a} over {b}")

    def evaluate(x: dict[str, Any]) -> dict[str, float]:
        mi = apply(_first_parts(x, sets))
        out: dict[str, float] = {}
        for n, st in zip(names, strategies, strict=True):
            c, o, _ = markov.totals(mi, st, rescale=True)
            out[f"{n} cost"], out[f"{n} {ou}"] = c, o
        if pair:
            a, b, label = pair
            out[label] = (s.wtp * out[f"{a} {ou}"] - out[f"{a} cost"]) - (s.wtp * out[f"{b} {ou}"] - out[f"{b} cost"])
        return out

    keys = sorted([*scalar, *sets], key=lambda k: labels[k])
    primary = pair[2] if pair else f"{names[0]} {ou}"
    return Problem(keys, {k: labels[k] for k in keys}, {**scalar, **{k: e for k, (e, _) in sets.items()}},
                   {k: points[k] for k in keys}, evaluate, primary, [], _ignored("markov", paths, labels),
                   units=s.cost_units if pair else ou, groups=_set_groups(sets))


def _sd(paths, opts: dict[str, Any]) -> Problem:
    from latris.operations import sd, uncertainty
    from latris.operations.sd_inference import simulate
    from latris.operations.sd_montecarlo import _with_draw, baseline_value, resolve_variables
    from latris.operations.sd_sensitivity import measure, metric_label, parse_metric

    model = sd.compile_project(root=paths.root)
    variable = opts.get("variable")
    (vid,) = resolve_variables(model, [variable] if variable else None)[:1]
    kind, at = parse_metric(opts.get("metric") or "final")
    specs = {k: v for k, v in uncertainty.sd_specs(paths).items()
             if (k in model.constants or k in model.stock_units) and k not in model.hidden}
    keys = sorted(specs, key=lambda k: model.labels.get(k, k))
    reference = simulate(model)
    if not reference.success:
        raise ValueError(f"the baseline run failed: {reference.message}")
    name = f"{model.labels[vid]} ({metric_label(kind, at, reference.time_units)})"

    def evaluate(x: dict[str, float]) -> dict[str, float]:
        res = simulate(_with_draw(model, x))
        if not res.success:
            raise ValueError(f"a run failed: {res.message}")
        return {name: measure(res.times, res.series[vid], kind, at)}

    fixed = sorted(model.labels.get(k, k) for k in model.constants if k not in specs and k not in model.hidden)
    return Problem(keys, {k: model.labels.get(k, k) for k in keys}, specs,
                   {k: baseline_value(model, k) for k in keys}, evaluate, name, fixed,
                   units=model.unit_text.get(vid, ""))


def _bn(paths, opts: dict[str, Any]) -> Problem:
    """Each table with a stated uncertainty ("worth n observations") is one input: a group of its rows'
    Dirichlets (a Noisy-OR table: a Beta around each cause's strength and the leak)."""
    from latris.operations import _bn_engine, bn, uncertainty
    from latris.operations._bn_canonical import expand_noisy_or
    from latris.operations._resolve import resolve_target
    from latris.operations.bn_inference import applied_likelihood
    from latris.operations.bn_montecarlo import _row_n
    from latris.operations.uncertainty import BN_TABLE
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate
    from latris.schema.attributes import ParameterUncertainty as PU

    variable = opts.get("variable")
    if not variable:
        raise ValueError("say which factor's probability to explain (variable), and optionally its state")
    sub = load_model(Substrate, paths.conceptual_yaml)
    labels = {e.id: e.label for e in sub.entities}
    ss_map = {e.target_id: e.states for e in bn._load_state_spaces(paths).entries}
    noisy = {e.target_id: e for e in bn._load_noisy_or(paths).entries}
    cpts = bn._effective_cpt_map(paths)
    target = resolve_target(variable, sub)
    if target not in cpts:
        raise ValueError(f"{labels.get(target, variable)} is not in the network")
    evidence = {resolve_target(k, sub): v for k, v in (opts.get("evidence") or {}).items()}
    if target in evidence:
        raise ValueError(f"{labels[target]} is observed; ask about a factor that isn't")
    states = ss_map[target]
    state = opts.get("state") or states[0]
    if state not in states:
        raise ValueError(f"{state!r} is not a state of {labels[target]} (states: {', '.join(states)})")
    specs = {k: v for k, v in uncertainty.bn_specs(paths).items() if k in cpts}
    groups: dict[str, list[list[float]]] = {}
    shown: dict[str, PU] = {}
    rows_of: dict[str, list[int]] = {}
    for node, node_specs in specs.items():
        if node in noisy:
            n = node_specs[BN_TABLE].params["n"]
            ne = noisy[node]
            groups[node] = [[n * ne.leak, n * (1 - ne.leak)]] + [[n * lk.prob, n * (1 - lk.prob)] for lk in ne.links]
        else:
            entry = cpts[node]
            parts, idx = [], []
            for j, row in enumerate(entry.rows):
                rn = _row_n(node_specs, entry.parents, row.parent_states)
                if rn:
                    parts.append([rn * p for p in row.p])
                    idx.append(j)
            if not parts:
                continue
            groups[node], rows_of[node] = parts, idx
        shown[node] = node_specs.get(BN_TABLE) or next(iter(node_specs.values()))
    given = ", ".join(f"{labels.get(k, k)} = {v}" for k, v in evidence.items())
    names = [f"P({labels[target]} = {st}" + (f" | {given})" if given else ")") for st in states]

    def evaluate(x: dict[str, Any]) -> dict[str, float]:
        tables = dict(cpts)
        for node, parts in x.items():
            if node in noisy:
                ne = noisy[node]
                drawn = ne.model_copy(update={"leak": parts[0][0], "links": [
                    lk.model_copy(update={"prob": p[0]}) for lk, p in zip(ne.links, parts[1:], strict=True)]})
                tables[node] = expand_noisy_or(drawn, ss_map)
            else:
                entry = cpts[node]
                rows = list(entry.rows)
                for j, p in zip(rows_of[node], parts, strict=True):
                    rows[j] = rows[j].model_copy(update={"p": p})
                tables[node] = entry.model_copy(update={"rows": rows})
        network = _bn_engine.build_network(ss_map, tables)
        applied = applied_likelihood(network, ss_map, evidence, {}, {})
        marg = _bn_engine.query_marginals(network, [target], evidence, likelihood=applied or None)[target]
        return {nm: marg[st] for nm, st in zip(names, states, strict=True)}

    keys = sorted(groups, key=lambda k: labels.get(k, k))
    fixed = sorted(labels.get(k, k) for k in cpts if k not in groups)
    return Problem(keys, {k: f"{labels.get(k, k)} (probability table)" for k in keys}, shown,
                   dict.fromkeys(keys), evaluate, names[states.index(state)], fixed, units="probability",
                   groups=groups)


@dataclass(frozen=True)
class Provider:
    build: Callable[[Any, dict[str, Any]], Problem]
    ranges_how: str  # the command that gives an input a range
    options: frozenset[str] = frozenset()  # what else it takes: SD a variable and metric, BN a variable,
    # a state and evidence
    default_n: tuple[int, int] = (512, 20)  # (Sobol base samples, Morris trajectories)
    keyed_by_output: bool = False  # recorded per output (SD: one result per variable and metric)


_PROVIDERS: dict[str, Provider] = {
    "fault_tree": Provider(lambda p, o: _risk("fault_tree", p, o), "latris ft uncertainty"),
    "bow_tie": Provider(lambda p, o: _risk("bow_tie", p, o), "latris bowtie uncertainty"),
    "event_tree": Provider(lambda p, o: _risk("event_tree", p, o), "latris et uncertainty"),
    "decision_tree": Provider(_dt, "latris dt range"),
    "markov": Provider(_markov, "latris markov range"),
    # SD runs are slower, so fewer by default; each variable and metric is its own result.
    "sd": Provider(_sd, "latris sd set-uncertainty", options=frozenset({"variable", "metric"}), default_n=(128, 10),
                   keyed_by_output=True),
    # A BN query is quick, but each table is a group of many columns; recorded per question asked.
    "bn": Provider(_bn, "latris bn set-uncertainty", options=frozenset({"variable", "state", "evidence"}),
                   default_n=(256, 20), keyed_by_output=True),
}


# ── the analysis ────────────────────────────────────────────────────


def analyse(model_type: str, *, method: str = "sobol", n: int | None = None, seed: int = 1234,
            output: str | None = None, variable: str | None = None, metric: str | None = None,
            state: str | None = None, evidence: dict[str, str] | None = None,
            root: Path | None = None) -> dict[str, Any]:
    """Sobol indices (``n`` base samples, a power of two) or Morris effects (``n`` trajectories) for each
    uncertain input of ``model_type``'s result. ``output`` picks the headline result; SD takes ``variable``
    and ``metric`` (final, peak, peak-time, min, mean, total, at:T) as its sensitivity analysis does; a BN
    takes ``variable`` (the factor asked about), ``state`` and ``evidence``."""
    import numpy as np

    if model_type not in _PROVIDERS:
        raise ValueError(f"global sensitivity analysis is for {', '.join(_PROVIDERS)}")
    if method not in METHODS:
        raise ValueError(f"method must be one of {', '.join(METHODS)}")
    provider = _PROVIDERS[model_type]
    given = {"variable": variable, "metric": metric, "state": state, "evidence": evidence}
    extra = sorted(k for k, v in given.items() if v and k not in provider.options)
    if extra:
        raise ValueError(f"{', '.join(extra)} {'doesn' if len(extra) == 1 else 'don'}'t apply here" + (
            f" (this analysis takes {', '.join(sorted(provider.options))})" if provider.options else ""))
    paths = require_project(root)
    prob = provider.build(paths, given)
    k = len(prob.keys)
    if k < 2:
        raise ValueError(f"global sensitivity needs at least two inputs with a range (`{provider.ranges_how}`); "
                         "with one, it explains all of the spread")
    n = n or provider.default_n[METHODS.index(method)]
    if method == "sobol" and (n < 16 or n & (n - 1)):
        raise ValueError("for Sobol, n (base samples) must be a power of two, at least 16")
    if method == "morris" and n < 4:
        raise ValueError("for Morris, n (trajectories) must be at least 4")
    runs = n * (k + 2) if method == "sobol" else n * (k + 1)
    if runs > MAX_RUNS:
        raise ValueError(f"{runs} model runs is more than {MAX_RUNS}; lower n")
    samplers = {key: smp.Sampler(prob.specs[key]) for key in prob.keys if key not in prob.groups}
    widths = prob.widths()
    cols = _columns(k, widths)
    names: list[str] = list(prob.evaluate(prob.point_values()))

    def f(u):
        decoded = {key: _decode_group(prob.groups[key], u[:, cols[i]]) if key in prob.groups
                   else [samplers[key].ppf(float(x)) for x in u[:, cols[i][0]]]
                   for i, key in enumerate(prob.keys)}
        rows = []
        for r in range(len(u)):
            out = prob.evaluate({key: v[r] for key, v in decoded.items()})
            rows.append([out[nm] for nm in names])
        return np.array(rows, dtype=float)

    import warnings

    with warnings.catch_warnings(), np.errstate(divide="ignore", invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)  # an output that doesn't vary has no indices (NaN)
        res = (sobol_indices(f, k, n, seed, widths) if method == "sobol"
               else morris_effects(f, k, n, seed, widths=widths))
    primary = prob.primary
    if output:
        match = [nm for nm in names if nm.casefold().startswith(output.casefold())]
        if len(match) != 1:
            raise ValueError(f"no single output matches {output!r}; outputs: {', '.join(names)}")
        primary = match[0]
    outputs = []
    for j, nm in enumerate(names):
        rows = []
        for i, key in enumerate(prob.keys):
            spec = prob.specs[key]
            sampler = samplers.get(key)
            row: dict[str, Any] = {"input": prob.labels[key], "distribution": spec.distribution,
                                   "point": prob.points.get(key), "reason": spec.reason,
                                   "weak": spec.verification != "human-verified" or spec.contested,
                                   "p5": sampler.quantile(0.05) if sampler else None,
                                   "p95": sampler.quantile(0.95) if sampler else None,
                                   "group": key in prob.groups}
            if key in prob.groups:
                row["n"] = spec.params.get("n")
            if method == "sobol":
                row.update({x: _num(res[x][i, j]) for x in ("S1", "ST", "S1_conf", "ST_conf")})
            else:
                row.update({x: _num(res[x][i, j]) for x in ("mu_star", "mu", "sigma", "mu_star_conf")})
            rows.append(row)
        rank = "ST" if method == "sobol" else "mu_star"
        rows.sort(key=lambda r: -(r[rank] if r[rank] is not None else -1))
        o: dict[str, Any] = {"output": nm, "indices": rows}
        if method == "sobol":
            o["variance"] = _num(res["variance"][j])
            o["mean"] = _num(res["mean"][j])
            s1 = [r["S1"] for r in rows if r["S1"] is not None]
            o["sum_S1"] = sum(s1) if s1 else None
        outputs.append(o)
    outputs.sort(key=lambda o: o["output"] != primary)
    return {"model_type": model_type, "method": method, "n": n, "seed": seed, "runs": res["runs"],
            "primary": primary, "outputs": outputs, "fixed": prob.fixed, "notes": prob.notes, "units": prob.units,
            "variable": variable, "metric": metric, "state": state, "evidence": dict(evidence or {})}


def _decode_group(parts: list[list[float]], u) -> list[list[list[float]]]:
    """Unit-uniform columns → each run's probabilities for every part of a Dirichlet group.

    Each component is a Gamma(α, 1) quantile of its own column, normalised within its part — the standard
    construction of a Dirichlet draw, so independent uniforms give exactly Dirichlet(α). A zero α stays 0.
    """
    import numpy as np
    from scipy.stats import gamma

    out: list[Any] = []
    c = 0
    for alpha in parts:
        a = np.asarray(alpha, dtype=float)
        m = len(a)
        g = np.where(a > 0, gamma.ppf(u[:, c:c + m], np.where(a > 0, a, 1.0)), 0.0)
        total = g.sum(axis=1, keepdims=True)
        point = a / a.sum()
        probs = np.where(total > 0, g / np.where(total > 0, total, 1.0), point)
        out.append(probs)
        c += m
    return [[p[r].tolist() for p in out] for r in range(len(u))]


def _share(x: float) -> float:
    """An index estimate as a share for prose: sampling noise can put it a little below 0 or above 1."""
    return min(max(x, 0.0), 1.0)


def _num(x: Any) -> float | None:
    v = float(x)
    return None if math.isnan(v) else v


def describe(p: dict[str, Any]) -> str:
    main = next(o for o in p["outputs"] if o["output"] == p["primary"])
    rows = main["indices"]
    if p["method"] == "sobol":
        if main.get("variance") in (None, 0):
            return f"{p['primary']} doesn't vary over the ranges given ({p['runs']} runs)"
        top = [r for r in rows if r["ST"] is not None][:3]
        parts = ", ".join(f"{r['input']} (total {_share(r['ST']):.0%}, alone {_share(min(r['S1'] or 0, r['ST'])):.0%})"
                          for r in top)
        s = f"Sobol indices for {p['primary']} over {p['runs']} runs: most of its variance comes from {parts}"
        if main["sum_S1"] is not None and main["sum_S1"] < 0.85:
            s += f"; inputs acting alone explain {_share(main['sum_S1']):.0%}, the rest is interaction"
        negligible = [r["input"] for r in rows if r["ST"] is not None and r["ST"] + (r["ST_conf"] or 0) < 0.01]
        if negligible:
            s += f"; {', '.join(negligible)} could be fixed without changing the spread"
        return s
    top = rows[:3]
    s = (f"Morris screening of {p['primary']} over {p['runs']} runs ({p['n']} trajectories): most influential "
         + ", ".join(f"{r['input']} (μ* {r['mu_star']:.3g})" for r in top))
    nonlinear = [r["input"] for r in rows if r["mu_star"] and r["sigma"] and r["sigma"] > 0.5 * r["mu_star"]]
    if nonlinear:
        s += f"; interacting or non-linear: {', '.join(nonlinear[:4])}"
    return s


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    mt = payload["model_type"]
    main = next(o for o in payload["outputs"] if o["output"] == payload["primary"])
    top = main["indices"][0] if main["indices"] else {}
    key = KINDS[mt] + (f"|{payload['primary']}" if _PROVIDERS[mt].keyed_by_output else "")
    sha, run = record_result(
        kind=KINDS[mt],
        key=key,
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm=("Sobol indices: Saltelli (2010) first-order and Jansen (1999) total estimators on a scrambled "
                   "Sobol sequence, bootstrap intervals" if payload["method"] == "sobol" else
                   f"Morris elementary effects, {MORRIS_LEVELS}-level grid, μ* (Campolongo et al. 2007)"),
        library_version="latris (numpy, scipy)",
        summary=describe(payload),
        model_type=mt,
        hyperparameters={"method": payload["method"], "n": payload["n"], "output": payload["primary"],
                         "state": payload.get("state"), "evidence": payload.get("evidence") or None,
                         "variable": payload.get("variable"), "metric": payload.get("metric")},
        uncertainty=True,
        seed=payload["seed"],
        metrics={"top_input": top.get("input"), "top_ST": top.get("ST"), "top_mu_star": top.get("mu_star")},
        commit_subject=f"Analysis: global sensitivity ({payload['method']}) of the {mt.replace('_', ' ')}",
        root=root,
    )
    return sha, run.id
