"""Monte Carlo uncertainty for the risk types — how sure is that probability or frequency?

A fault tree's top-event probability, a bow-tie's layer-of-protection
frequencies and an event tree's end-state frequencies are all computed from
point values that are rarely known exactly. Here each input can carry a
distribution (stored with the other parameter uncertainty, with provenance):

- fault tree: a basic event's probability (cell ``fault_tree:probability``);
- bow-tie: a barrier's probability of failure on demand (``bow_tie:pfd``) or a
  threat's frequency (``bow_tie:frequency``);
- event tree: a heading's P(yes), in general or given earlier answers
  (``event_tree:probability[:<heading>=<answer>,…]``), or the initiating
  frequency (``event_tree:frequency``).

Probabilistic risk assessment conventionally describes such a value as a
lognormal by its median and *error factor* (the 95th percentile over the
median; NUREG/CR-2300); :func:`error_factor_lognormal` converts that to the
stored mean and standard deviation. Probabilities are kept within [0, 1] and
frequencies non-negative by truncation.

The Monte Carlo samples every input that has a distribution (Latin hypercube
by default, seeded), recomputes the result through the type's own engine and
reports percentiles, the mean against the point estimate (for skewed inputs
the mean is higher — the point estimate is not the expected value) and which
inputs drive the spread (Spearman rank correlation). Each input is sampled
once per run, so a barrier on several lines, or an event under several gates,
takes the same value everywhere in that run — the state-of-knowledge
dependence that sampling each occurrence separately would miss.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from latris.operations import _sampling as smp
from latris.operations import uncertainty as unc
from latris.operations._resolve import resolve_entity
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.attributes import ParameterUncertainty
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification

MODEL_TYPES = ("fault_tree", "bow_tie", "event_tree")
KINDS = {"fault_tree": "ft-monte-carlo", "bow_tie": "bt-monte-carlo", "event_tree": "et-monte-carlo"}
Z95 = 1.6448536269514722
MAX_RUNS = 100_000


def error_factor_lognormal(median: float, error_factor: float) -> dict[str, float]:
    """Lognormal mean and sd from a median and error factor (95th percentile / median)."""
    if median <= 0:
        raise ValueError("the median must be positive")
    if error_factor <= 1:
        raise ValueError("the error factor (95th percentile over the median) must be greater than 1")
    sigma = math.log(error_factor) / Z95
    mean = median * math.exp(sigma**2 / 2)
    return {"mean": mean, "sd": mean * math.sqrt(math.exp(sigma**2) - 1)}


# ── what can be uncertain, and its point value ───────────────────────


def _given_key(given) -> str:
    return ",".join(f"{h}={a}" for h, a in sorted(given))


def _cell(model_type: str, quantity: str, given_key: str = "") -> str:
    return f"{model_type}:{quantity}" + (f":{given_key}" if given_key else "")


def _target(model_type: str, target: str, given: list[tuple[str, str]] | None, paths) -> dict[str, Any]:
    """Resolve what is uncertain: {id, label, cell, quantity ("probability"/"frequency"), value}."""
    sub = load_model(Substrate, paths.conceptual_yaml)
    ent = resolve_entity(target, sub.entities)
    if model_type == "fault_tree":
        from latris.operations import fault_tree as ft

        if given:
            raise ValueError("--given applies to event-tree headings only")
        if ft.get_events(root=paths.root).get(ent.id) not in ("basic_event", "undeveloped_event"):
            raise ValueError(f"{ent.label} isn't a basic or undeveloped event; only those have probabilities")
        cur = next((p for p in ft.get_probabilities(root=paths.root).entries if p.target_id == ent.id), None)
        if cur is None:
            raise ValueError(f"{ent.label} has no probability yet; set one (`latris ft probability`) first")
        return {"id": ent.id, "label": ent.label, "cell": _cell(model_type, "probability"),
                "quantity": "probability", "value": cur.probability}
    if model_type == "bow_tie":
        from latris.operations import bow_tie as bt

        if given:
            raise ValueError("--given applies to event-tree headings only")
        role = bt.get_elements(root=paths.root).get(ent.id)
        if role == "barrier":
            cur = next((b for b in bt.get_barriers(root=paths.root).entries if b.target_id == ent.id), None)
            if cur is None or cur.pfd is None:
                raise ValueError(f"{ent.label} has no failure probability yet; set one (`latris bowtie barrier "
                                 "--pfd`) first")
            if cur.status == "not_in_place":
                raise ValueError(f"{ent.label} is not in place, so it always fails; it has nothing uncertain")
            return {"id": ent.id, "label": ent.label, "cell": _cell(model_type, "pfd"), "quantity": "probability",
                    "value": cur.pfd}
        if role == "threat":
            cur = next((f for f in bt.get_frequencies(root=paths.root).entries if f.target_id == ent.id), None)
            if cur is None:
                raise ValueError(f"{ent.label} has no frequency yet; set one (`latris bowtie frequency`) first")
            return {"id": ent.id, "label": ent.label, "cell": _cell(model_type, "frequency"),
                    "quantity": "frequency", "value": cur.frequency}
        raise ValueError(f"{ent.label} is neither a barrier nor a threat; only their numbers can be uncertain")
    from latris.operations import event_tree as et

    role = et.get_elements(root=paths.root).get(ent.id)
    if role == "initiating_event":
        if given:
            raise ValueError("--given applies to headings, not the initiating event")
        cur = next((f for f in et.get_frequencies(root=paths.root).entries if f.target_id == ent.id), None)
        if cur is None:
            raise ValueError(f"{ent.label} has no frequency yet; set one (`latris et frequency`) first")
        return {"id": ent.id, "label": ent.label, "cell": _cell(model_type, "frequency"), "quantity": "frequency",
                "value": cur.frequency}
    if role != "functional_event":
        raise ValueError(f"{ent.label} is neither a heading nor the initiating event")
    cond = [(resolve_entity(h, sub.entities).id, a) for h, a in (given or [])]
    want = frozenset(cond)
    cur = next((p for p in et.get_probabilities(root=paths.root).entries
                if p.target_id == ent.id and frozenset((c.heading, c.answer) for c in p.given) == want), None)
    if cur is None:
        where = f" given {', '.join(f'{h}={a}' for h, a in given or [])}" if given else ""
        raise ValueError(f"{ent.label} has no probability{where} yet; set it (`latris et probability`) first")
    return {"id": ent.id, "label": ent.label, "cell": _cell(model_type, "probability", _given_key(cond)),
            "quantity": "probability", "value": cur.p_yes}


def _bounded(distribution: str, params: dict[str, float], quantity: str) -> dict[str, float]:
    """Keep a probability in [0, 1] and a frequency non-negative, truncating where the family allows."""
    p = dict(params)
    if distribution in ("normal", "lognormal", "gamma"):
        if distribution == "normal":
            p.setdefault("min", 0.0)
        if quantity == "probability":
            p.setdefault("max", 1.0)
    lo, hi = (0.0, 1.0) if quantity == "probability" else (0.0, math.inf)
    # A missing min or max is the distribution's own check to report (ParameterUncertainty), not a KeyError.
    if distribution in ("uniform", "triangular") and not (lo <= p.get("min", lo) and p.get("max", hi) <= hi):
        raise ValueError(f"a {quantity} must lie in [{lo:g}, {hi:g}]; this range goes outside it")
    if distribution == "beta" and not (lo <= p.get("min", 0.0) and p.get("max", 1.0) <= hi):
        raise ValueError(f"a {quantity} must lie in [{lo:g}, {hi:g}]; this range goes outside it")
    return p


def set_uncertainty(
    model_type: str,
    target: str,
    distribution: str,
    params: dict[str, float],
    *,
    given: list[tuple[str, str]] | None = None,
    reason: str = "",
    source_id: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    verification: ProvenanceVerification = "unverified",
    root: Path | None = None,
) -> tuple[ParameterUncertainty, str]:
    """Give a risk model's probability or frequency a distribution (replacing any previous one).

    ``params`` may be ``{"median": m, "error_factor": ef}`` for a lognormal, converted to mean and sd.
    """
    if model_type not in MODEL_TYPES:
        raise ValueError(f"Monte Carlo uncertainty here is for {', '.join(MODEL_TYPES)}")
    paths = require_project(root)
    t = _target(model_type, target, given, paths)
    params = dict(params)
    if "median" in params or "error_factor" in params:
        if distribution != "lognormal" or set(params) - {"median", "error_factor", "min", "max"} \
                or not {"median", "error_factor"} <= set(params):
            raise ValueError("a median and error factor describe a lognormal: give both, and nothing but "
                             "optional min/max")
        m, ef = params.pop("median"), params.pop("error_factor")
        params.update(error_factor_lognormal(m, ef))
        reason = f"median {m:g}, error factor {ef:g}" + (f"; {reason}" if reason else "")
    params = _bounded(distribution, params, t["quantity"])
    entry = ParameterUncertainty(target_id=t["id"], distribution=distribution, params=params,  # type: ignore[arg-type]
                                 parameter_cell_id=t["cell"], reason=reason, source_id=source_id, origin=origin,
                                 verification=verification)
    sampler = smp.Sampler(entry)
    lo, hi = sampler.quantile(0.001), sampler.quantile(0.999)
    if not lo <= t["value"] <= hi:
        raise ValueError(f"{t['label']}'s current {t['quantity']} {t['value']:g} lies outside this distribution "
                         f"(99.8% of it is between {lo:.3g} and {hi:.3g})")
    s = unc.load(paths)
    s.entries = [e for e in s.entries if not (e.target_id == t["id"] and e.parameter_cell_id == t["cell"])] + [entry]
    path = paths.parameter_uncertainty_yaml
    dump_model(s, path)
    pretty = ", ".join(f"{k}={v:.4g}" for k, v in entry.params.items())
    subject = f"Set uncertainty on {t['label']} ({t['quantity']}): {distribution}({pretty})"
    sha = auto_commit(paths.root, subject=subject,
                      body=f"target: {t['id']}\ncell: {t['cell']}\norigin: {origin}\nsource_id: {source_id}\n"
                           f"reason: {reason}", paths=[path])
    return entry, sha


def clear_uncertainty(model_type: str, target: str, *, given: list[tuple[str, str]] | None = None,
                      root: Path | None = None) -> str:
    paths = require_project(root)
    t = _target(model_type, target, given, paths)
    s = unc.load(paths)
    kept = [e for e in s.entries if not (e.target_id == t["id"] and e.parameter_cell_id == t["cell"])]
    if len(kept) == len(s.entries):
        raise ValueError(f"{t['label']} has no uncertainty range to clear")
    s.entries = kept
    dump_model(s, paths.parameter_uncertainty_yaml)
    return auto_commit(paths.root, subject=f"Clear uncertainty on {t['label']}",
                       paths=[paths.parameter_uncertainty_yaml])


def specs(model_type: str, paths) -> dict[str, ParameterUncertainty]:
    """This type's ranges by cell key ``<target id>|<cell>``."""
    return {f"{e.target_id}|{e.parameter_cell_id}": e for e in unc.load(paths).entries
            if (e.parameter_cell_id or "").startswith(f"{model_type}:") and e.distribution != "unknown"}


# ── the models, as functions of their inputs ─────────────────────────


class _Model:
    """Point inputs by cell key, their labels, and a function from inputs to named outputs."""

    def __init__(self, inputs: dict[str, float], labels: dict[str, str], evaluate, primary: str, quantity: str):
        self.inputs, self.labels, self.evaluate, self.primary, self.quantity = (inputs, labels, evaluate, primary,
                                                                                quantity)


def _labels(predictor) -> dict[str, str]:  # noqa: ANN001
    return {c.key: c.label for c in predictor.inputs() if c.key in predictor.point}


# The functions themselves are the predictors' (``operations/predictors``): a prediction and a sampled run
# go through the same code.


def _ft_model(paths) -> _Model:
    from latris.operations.predictors import fault_tree

    p = fault_tree.build(paths)
    if p.incomplete:
        raise ValueError(p.problems[0])
    if p.missing:
        raise ValueError(f"no probability yet for {', '.join(p.missing)}; Monte Carlo needs every basic event's value")
    top_id: str = p.top  # type: ignore[assignment]  # a complete tree has one
    top = p.labels[top_id]

    def evaluate(x: dict[str, float]) -> dict[str, float]:
        return {top: p.evaluate(x)[top_id]}

    return _Model(dict(p.point), _labels(p), evaluate, top, "probability")


def _bt_model(paths) -> _Model:
    from latris.operations.predictors import bow_tie

    p = bow_tie.build(paths)
    if p.problems:
        raise ValueError(p.problems[0])
    top: str = p.bt.top  # type: ignore[assignment]  # a complete bow-tie has one
    names = {e: f"{p.labels[e]} (per year)" for e in [top, *(ln.end for ln in p.bt.right)]}

    def evaluate(x: dict[str, float]) -> dict[str, float]:
        return {names[e]: v for e, v in p.evaluate(x).items()}

    return _Model(dict(p.point), _labels(p), evaluate, names[top], "frequency")


def _et_model(paths) -> _Model:
    from latris.operations.predictors import event_tree

    p = event_tree.build(paths)
    if p.problems:
        raise ValueError(p.problems[0])
    unit = " (per year)" if p.fkey else " (probability)"

    def evaluate(x: dict[str, float]) -> dict[str, float]:
        return {p.labels[e] + unit: v for e, v in p.evaluate(x).items()}

    point = evaluate(p.point)
    rarest = min(point, key=lambda n: (point[n], n))  # the usual concern: the rare, bad end state
    return _Model(dict(p.point), dict(p.input_labels), evaluate, rarest, "frequency" if p.fkey else "probability")


_BUILD = {"fault_tree": _ft_model, "bow_tie": _bt_model, "event_tree": _et_model}


def _summary(values: list[float], point: float) -> dict[str, Any]:
    s = sorted(values)
    mean = math.fsum(s) / len(s)
    return {"point": point, "mean": mean, "p5": smp.percentile(s, 5), "p50": smp.percentile(s, 50),
            "p95": smp.percentile(s, 95), "min": s[0], "max": s[-1],
            "mean_over_point": mean / point if point > 0 else None,
            "share_above_point": sum(1 for v in s if v > point) / len(s)}


def _is_probability(key: str) -> bool:
    return not key.split("|", 1)[1].endswith(":frequency")


def monte_carlo(model_type: str, *, runs: int = 2000, seed: int = 1234, sampling: str = "lhs",
                output: str | None = None, root: Path | None = None) -> dict[str, Any]:
    """Sample every input with a distribution; summarise each output and rank what drives it.

    ``output`` picks the headline result (an event tree's end state, a bow-tie's consequence); by default the
    top event, or an event tree's rarest end state.
    """
    if model_type not in _BUILD:
        raise ValueError(f"Monte Carlo here is for {', '.join(MODEL_TYPES)}")
    if not 10 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be between 10 and {MAX_RUNS}")
    paths = require_project(root)
    model = _BUILD[model_type](paths)
    ranges = {k: v for k, v in specs(model_type, paths).items() if k in model.inputs}
    if not ranges:
        raise ValueError("no input has an uncertainty range yet; give some a distribution first "
                         "(e.g. `latris ft uncertainty <event> lognormal --median 1e-3 --error-factor 3`)")
    draws = smp.sample(ranges, runs, seed=seed, method=sampling)
    point_out = model.evaluate(model.inputs)
    outputs: dict[str, list[float]] = {n: [] for n in point_out}
    for d in draws:
        x = {**model.inputs, **{k: min(max(v, 0.0), 1.0) if _is_probability(k) else max(v, 0.0)
                                for k, v in d.items()}}
        for n, v in model.evaluate(x).items():
            outputs[n].append(v)
    primary = model.primary
    if output:
        match = [n for n in outputs if n.casefold().startswith(output.casefold())]
        if len(match) != 1:
            raise ValueError(f"no single output matches {output!r}; outputs: {', '.join(outputs)}")
        primary = match[0]
    keys = sorted(ranges, key=lambda k: model.labels[k])
    correlations = {n: {model.labels[k]: smp.spearman([d[k] for d in draws], v) for k in keys}
                    for n, v in outputs.items()}
    drivers = []
    for k in keys:
        rho = correlations[primary][model.labels[k]]
        e = ranges[k]
        drivers.append({"input": model.labels[k], "point": model.inputs[k], "distribution": e.distribution,
                        "params": e.params, "reason": e.reason, "origin": e.origin, "source": e.source_id,
                        "weak": e.verification != "human-verified" or e.contested,
                        "p5": smp.Sampler(e).quantile(0.05), "p95": smp.Sampler(e).quantile(0.95),
                        "spearman": rho})
    drivers.sort(key=lambda r: -abs(r["spearman"] or 0))
    fixed = sorted(model.labels[k] for k in model.inputs if k not in ranges)
    return {
        "model_type": model_type, "quantity": model.quantity, "primary": primary,
        "runs": runs, "seed": seed, "sampling": sampling,
        "outputs": [{"output": n, **_summary(v, point_out[n])} for n, v in outputs.items()],
        "drivers": drivers, "correlations": correlations, "fixed": fixed,
    }


def _g(x: float | None) -> str:
    return "—" if x is None else f"{x:.3g}"


def describe(p: dict[str, Any]) -> str:
    main = next(o for o in p["outputs"] if o["output"] == p["primary"])
    top = p["drivers"][0] if p["drivers"] else None
    s = (f"{p['primary']}: 90% of {p['runs']} runs between {_g(main['p5'])} and {_g(main['p95'])} "
         f"(median {_g(main['p50'])}, mean {_g(main['mean'])}, point estimate {_g(main['point'])})")
    if top and top["spearman"] is not None:
        s += f"; most of the spread comes from {top['input']} (rank correlation {top['spearman']:.2f})"
    if p["fixed"]:
        s += f"; {len(p['fixed'])} input(s) held at their point value"
    return s


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    main = next(o for o in payload["outputs"] if o["output"] == payload["primary"])
    sha, run = record_result(
        kind=KINDS[payload["model_type"]],
        key=KINDS[payload["model_type"]],
        payload=payload,
        purpose="sensitivity-analysis",
        algorithm=f"Monte Carlo ({'Latin hypercube' if payload['sampling'] == 'lhs' else 'random'} sampling) "
                  "through the model's own calculation; Spearman rank correlation for drivers",
        library_version="latris",
        summary=describe(payload),
        model_type=payload["model_type"],
        hyperparameters={"runs": payload["runs"], "sampling": payload["sampling"], "output": payload["primary"]},
        uncertainty=True,
        seed=payload["seed"],
        metrics={"p5": main["p5"], "p50": main["p50"], "p95": main["p95"], "mean": main["mean"],
                 "point": main["point"]},
        commit_subject=f"Analysis: Monte Carlo on the {payload['model_type'].replace('_', ' ')}",
        root=root,
    )
    return sha, run.id
