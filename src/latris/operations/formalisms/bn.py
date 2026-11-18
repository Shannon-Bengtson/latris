"""Bayesian networks as a formalism plugin — the oldest quantitative type, wired into the registry.

Everything report-facing about BN lives here: the four recorded result kinds (query, explanation,
Monte Carlo over the tables, parameter sensitivity) with their Markdown renderers, interpretation
claims and chart markers; the build-spec block (check/apply/export for share links); and the
Mermaid sketch (states, observed evidence, query target). Kind strings are unchanged from the
pre-registry wiring, so recorded runs, staleness and share links keep working.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from latris.operations.formalisms import Formalism, ResultKind, default_origin, register

_REVIEWED = "human-verified"


# ── results: render ──────────────────────────────────────────────────


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _given(p: dict[str, Any]) -> str:
    from latris.operations.bn import evidence_description

    labels = p.get("labels", {})
    observed = evidence_description(p.get("evidence", {}), p.get("soft"), p.get("likelihood"), labels)
    do = p.get("interventions") or {}
    text = observed
    if do:
        set_text = "we set " + ", ".join(f"{labels.get(k, k)} = {v}" for k, v in sorted(do.items()))
        text = f"{set_text} and {observed}" if observed else set_text
    if p.get("scenario"):
        tables = [c for c in p.get("scenario_changes", []) if c.startswith("P(")]
        what = f"scenario {p['scenario']}" + (f" ({'; '.join(tables)})" if tables else "")
        text = f"{what}: {text}" if text else what
    return text


def _subtitle_given(p: dict[str, Any]) -> str:
    given = _given(p)
    return f"given {given}" if given else "no evidence (prior)"


def _subtitle_target(p: dict[str, Any]) -> str:
    labels = p.get("labels", {})
    target = p.get("target") or p.get("target_id")
    state = p.get("focus_state") or p.get("target_state")
    head = f"P({labels.get(target, target)} = {state})" if target and state else ""
    given = _given(p)
    return f"{head} given {given}" if given and head else head


def _render_query(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _MAX_ROWS, _table

    labels = p["labels"]
    given = _given(p)
    out = [f"Given {given}:" if given else "With no evidence (prior probabilities):", ""]
    rows = []
    for node in sorted(p["posteriors"], key=lambda n: labels.get(n, n))[:_MAX_ROWS]:
        for state, prob in p["posteriors"][node].items():
            prior = p["priors"].get(node, {}).get(state)
            rows.append([labels.get(node, node), state, _pct(prior) if given else "", _pct(prob)])
    headers = ["Node", "State", "Prior", "Posterior"] if given else ["Node", "State", "", "Probability"]
    out += _table(headers, rows)
    return out


def _render_explanation(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _table

    labels = p["labels"]
    given = _given(p) or "no evidence"
    what = "every unobserved factor" if p["kind"] == "MPE" else "the factors asked about"
    prob = f" Its probability given the evidence: {_pct(p['probability'])}." if p.get("probability") is not None else ""
    out = [f"The single most likely combination of states of {what}, given {given}.{prob}", ""]
    rows = []
    for r in p["rows"]:
        if r.get("alternatives_impossible"):
            vs = "alternatives impossible"
        elif r.get("times_likelier") is not None:
            vs = f"{r['times_likelier']:.3g}× likelier than {r['runner_up']}"
        else:
            vs = "—"
        rows.append([labels.get(r["node"], r["node"]), r["state"], _pct(r["marginal"]), vs])
    out += _table(["Factor", "Most likely", "Its own probability", "Against its runner-up"], rows)
    differs = [r for r in p["rows"] if r.get("differs_from_marginal")]
    for r in differs:
        out.append(
            f"On its own, {labels.get(r['node'], r['node'])} is likelier to be {r['favourite']}; it's "
            f"{r['state']} in the most likely combination because of how it fits with the other factors."
        )
    if differs:
        out.append("")
    if p.get("note"):
        out += [f"_{p['note']}_", ""]
    return out


def _render_monte_carlo(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _grounding, _table
    from latris.operations.bn_montecarlo import describe

    out = [
        describe(p) + ".",
        "",
        f"{p['runs']} draws of the uncertain probability tables (seed {p['seed']}); the point estimate uses the "
        "tables as they stand.",
        "",
    ]
    rows = []
    for st in p["states"]:
        b = p["by_state"][st]
        rows.append(
            [
                st,
                _pct(b["point"]),
                _pct(b["p50"]),
                f"{_pct(b['p25'])}–{_pct(b['p75'])}",
                f"{_pct(b['p2.5'])}–{_pct(b['p97.5'])}",
            ]
        )
    out += _table(["State", "Point estimate", "Median", "50% of draws", "95% of draws"], rows)
    out.append("Tables sampled:")
    out.append("")
    for t in p["tables"]:
        if t["fixed"]:
            continue
        n = f"worth about {t['n']:g} observations" if t.get("n") else "some rows uncertain"
        why = f" — {t['reason']}" if t.get("reason") else ""
        out.append(f"- {t['label']}: {n}{why} ({_grounding(t.get('origin'), t.get('verification'))})")
    fixed = [t["label"] for t in p["tables"] if t["fixed"]]
    if fixed:
        out.append(f"- Held fixed: {', '.join(fixed)}")
    out.append("")
    drivers = [d for d in p["drivers"] if d["rho"] is not None and abs(d["rho"]) >= 0.1][:3]
    if drivers:
        listed = ", ".join(f"{d['label']} (rank correlation {d['rho']:+.2f})" for d in drivers)
        out += [f"What drives the spread: {listed}.", ""]
    return out


def _render_options(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _table

    given = _given(p)
    draws = (f"Every option was asked on the same {p['runs']} draws of the uncertain tables "
             f"({', '.join(p['uncertain'])}; seed {p['seed']}), so each difference from its reference is "
             "measured draw by draw." if p["runs"] else
             "Point probabilities: no table has a stated uncertainty, so there is no spread to show.")
    out = [
        f"P({p['label']} = {p['focus_state']}){' given ' + given if given else ''}. {draws} Differences are in "
        "percentage points (positive: higher than the reference). The baseline is the network with no scenario "
        "changes; a scenario's overridden rows and the factors it sets are held at its values.",
        "",
    ]
    rows = []
    for r in p["options"]:
        d = r.get("difference")
        row = ["Baseline (no scenario changes)" if r["name"] == "baseline" else r["name"], _pct(r["point"])]
        if p["runs"]:
            row.append(f"{_pct(r['p2.5'])}–{_pct(r['p97.5'])}")
        row.append(r.get("reference", "baseline") if d else "—")
        if d:
            diff = f"{d['point'] * 100:+.3g}"
            if "p2.5" in d:
                diff += f" ({d['p2.5'] * 100:+.3g} to {d['p97.5'] * 100:+.3g})"
            row.append(diff)
        else:
            row.append("—")
        if p["runs"]:
            row.append(f"{d['share_lower']:.0%} / {d['share_higher']:.0%}" if d else "—")
        row.append("; ".join(r.get("changes", [])) or "—")
        rows.append(row)
    headers = ["Option", "Probability"] + (["95% of draws"] if p["runs"] else []) + ["Compared with",
               "Difference (points" + (", 95%)" if p["runs"] else ")")]
    headers += (["Draws lower / higher"] if p["runs"] else []) + ["What it changes"]
    out += _table(headers, rows)
    for w in p.get("warnings", []):
        out += [f"> ⚠ {w}", ""]
    return out


def _claims_options(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations._compare import arm_label
    from latris.operations.bn_compare import describe_option

    head = f"Options compared on P({p['label']} = {p['focus_state']})"
    head += f", {p['runs']} paired draws of the uncertain tables" if p["runs"] else ", point probabilities"
    out["answer_to_question"].append(head + ". Each difference is measured against the arm named after 'vs':")
    for r in p["options"]:
        out["answer_to_question"].append("  - " + describe_option(p, r))
    for r in p["options"]:
        d = r.get("difference")
        if not d:
            continue
        if "share_lower" in d and 0.1 < d["share_lower"] < 0.9:
            out["confidence_assessment"].append(
                f"Whether {r['name']} gives a lower P({p['label']} = {p['focus_state']}) than "
                f"{arm_label(r.get('reference', 'baseline'))} is uncertain: lower in {d['share_lower']:.0%} of "
                f"draws, higher in {d['share_higher']:.0%}."
            )
        else:
            out["implications"].append(describe_option(p, r) + ".")
    if not p["runs"]:
        out["confidence_assessment"].append(
            f"The comparison on P({p['label']} = {p['focus_state']}) uses point probabilities: no table has a "
            "stated uncertainty, so how sure the differences are isn't shown."
        )
    for w in p.get("warnings", []):
        out["open_questions"].append(w)


def _render_sensitivity(p: dict[str, Any]) -> list[str]:
    from latris.exporters.results import _MAX_ROWS, _grounding, _table

    labels = p.get("labels", {})  # baked in at record time; runs from before then show ids
    target = labels.get(p["target_id"], p["target_id"])
    out = [f"Which probabilities move P({target} = {p['target_state']}) (baseline {_pct(p['baseline'])}):", ""]
    rows = []
    for f in p["findings"][:_MAX_ROWS]:
        given = ", ".join(f"{labels.get(k, k)}={v}" for k, v in f["parent_states"].items())
        cell = f"P({labels.get(f['node_id'], f['node_id'])}={f['state']}{' | ' + given if given else ''})"
        rows.append(
            [
                cell,
                _pct(f["baseline_prob"]),
                f"{_pct(f.get('low', 0.0))}–{_pct(f.get('high', 1.0))} "
                f"({f.get('range_source', 'any value from 0 to 1')})",
                f"{f['influence'] * 100:.1f} points",
                _grounding(f.get("origin"), f.get("verification")),
            ]
        )
    out += _table(["Probability", "Value", "Range tried", "Target moves by up to", "Grounding"], rows)
    return out


# ── results: interpretation claims ───────────────────────────────────


def _who(origin: str | None) -> str:
    return {"ai-proposed": "AI-proposed", "data-derived": "derived from data", "human-elicited": "elicited"}.get(
        origin or "", "entered"
    )


def _soft_question(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels = p.get("labels", {})
    for k, dist in sorted((p.get("soft") or {}).items()):
        state = max(dist, key=dist.get)  # type: ignore[arg-type]
        question = (
            f"How sure are we that {labels.get(k, k)} is {state}? The analysis takes it as {dist[state]:.0%} — "
            "an estimate entered by hand, not an observation."
        )
        if question not in out["open_questions"]:
            out["open_questions"].append(question)


def _claims_query(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels = p["labels"]
    if not (p["evidence"] or p.get("soft") or p.get("likelihood") or p.get("interventions")):
        return
    _soft_question(p, out)
    given = _given(p)
    for node in sorted(p["posteriors"], key=lambda n: labels.get(n, n))[:4]:
        dist = p["posteriors"][node]
        state = max(dist, key=dist.get)  # type: ignore[arg-type]
        prior = p["priors"].get(node, {}).get(state)
        before = f" (prior {prior * 100:.0f}%)" if prior is not None else ""
        out["answer_to_question"].append(
            f"Given {given}, P({labels.get(node, node)} = {state}) = {dist[state] * 100:.0f}%{before}."
        )


def _claims_explanation(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    from latris.operations.bn import describe_explanation

    out["answer_to_question"].append(describe_explanation(p) + ".")
    _soft_question(p, out)
    labels = p["labels"]
    weak = [r for r in p["rows"] if r.get("times_likelier") is not None and r["times_likelier"] < 1.5]
    for r in weak:
        out["confidence_assessment"].append(
            f"In the most likely explanation, {labels.get(r['node'], r['node'])} = {r['state']} is only "
            f"{r['times_likelier']:.2g}× likelier than {r['runner_up']} — close to a coin-flip."
        )


def _claims_monte_carlo(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels = p["labels"]
    s = p["focus_state"]
    b = p["by_state"][s]
    given = _given(p)
    cond = f" | {given}" if given else ""
    claim = (
        f"P({labels.get(p['target'], p['target'])} = {s}{cond}) is between {b['p2.5']:.0%} and {b['p97.5']:.0%} "
        f"in 95% of {p['runs']} draws of the uncertain probability tables (point estimate {b['point']:.0%})."
    )
    out["sensitivity"].append(claim)
    out["confidence_assessment"].append(claim)
    _soft_question(p, out)
    tables = {t["node"]: t for t in p["tables"]}
    drivers = [d for d in p["drivers"] if d["rho"] is not None and abs(d["rho"]) >= 0.3]
    if drivers:
        top = drivers[0]
        t = tables.get(top["node"], {})
        unreviewed = t.get("verification") != _REVIEWED
        note = f", and its uncertainty is {_who(t.get('origin'))} and not yet reviewed" if unreviewed else ""
        out["sensitivity"].append(f"The spread comes mostly from {top['label']}'s probability table{note}.")
        if unreviewed:
            out["open_questions"].append(
                f"How well is {top['label']}'s probability table known? It drives most of the uncertainty in "
                f"P({labels.get(p['target'], p['target'])} = {s})."
            )


def _claims_sensitivity(p: dict[str, Any], out: dict[str, list[str]]) -> None:
    labels = p.get("labels", {})  # baked in at record time; runs from before then show ids
    target = f"P({labels.get(p['target_id'], p['target_id'])} = {p['target_state']})"
    top = p["findings"][:3]
    if not top:
        return
    listed = ", ".join(
        f"P({labels.get(f['node_id'], f['node_id'])} = {f['state']}) (up to {f['influence'] * 100:.0f} points)"
        for f in top
    )
    out["sensitivity"].append(f"{target} is most sensitive to {listed}.")
    for f in top:
        if f.get("weak"):
            out["open_questions"].append(
                f"P({labels.get(f['node_id'], f['node_id'])} = {f['state']}) strongly affects {target} but is not "
                f"yet reviewed."
            )


# ── results: run and replay ──────────────────────────────────────────


def _run_query(a, root: Path) -> str:
    from latris.operations import bn as bn_ops

    result = bn_ops.infer(query=a.query or None, evidence=a.evidence or None, soft=a.soft or None,
                          likelihood=a.likelihood or None, interventions=a.interventions or None,
                          scenario=a.scenario, root=root)
    return bn_ops.record_query(result, root=root)[1]


def _run_explain(a, root: Path) -> str:
    from latris.operations import bn as bn_ops

    out = bn_ops.explain(over=a.over or None, evidence=a.evidence or None, soft=a.soft or None,
                         likelihood=a.likelihood or None, root=root)
    return bn_ops.record_explanation(out, root=root)[1]


def _run_monte_carlo(a, root: Path) -> str:
    from latris.operations import bn as bn_ops

    if not a.target:
        raise ValueError("a BN Monte Carlo needs a target")
    out = bn_ops.run_monte_carlo(
        a.target, state=a.state, evidence=a.evidence or None, soft=a.soft or None,
        likelihood=a.likelihood or None, runs=a.runs or 500, seed=a.seed if a.seed is not None else 1234,
        scenario=a.scenario, root=root,
    )
    return bn_ops.record_monte_carlo(out, root=root)[1]


def _run_compare(a, root: Path) -> str:
    from latris.operations import bn as bn_ops

    if not a.target or not a.scenarios:
        raise ValueError("a BN comparison needs a target and at least one scenario")
    out = bn_ops.run_compare(
        a.target, a.scenarios, state=a.state, evidence=a.evidence or None, soft=a.soft or None,
        likelihood=a.likelihood or None, reference=a.reference, runs=a.runs if a.runs is not None else 500,
        seed=a.seed if a.seed is not None else 1234, root=root,
    )
    return bn_ops.record_compare(out, root=root)[1]


def _run_sensitivity(a, root: Path) -> str:
    from latris.operations import bn_sensitivity

    if not a.target or not a.state:
        raise ValueError("a BN sensitivity analysis needs a target and a state")
    result = bn_sensitivity.sensitivity(a.target, a.state, evidence=a.evidence or None, root=root)
    return bn_sensitivity.record_sensitivity(result, root=root)[1]


def _relabeled(p: dict[str, Any]) -> dict[str, str]:
    """Id → label map for replaying a recorded run: baked into the payload, else the live substrate."""
    labels = p.get("labels")
    if labels is None:  # recorded before labels were baked in
        from latris.repo.project import require_project
        from latris.repo.yaml_io import load_model
        from latris.schema import Substrate

        labels = {e.id: e.label for e in load_model(Substrate, require_project().conceptual_yaml).entities}
    return labels


def _def_query(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    labels = p.get("labels", {})
    return make_analysis(
        kind="bn_query",
        evidence={labels.get(k, k): v for k, v in p["evidence"].items()},
        soft={labels.get(k, k): v for k, v in (p.get("soft") or {}).items()},
        likelihood={labels.get(k, k): v for k, v in (p.get("likelihood") or {}).items()},
        interventions={labels.get(k, k): v for k, v in (p.get("interventions") or {}).items()},
        query=[labels.get(n, n) for n in p["posteriors"]],
        scenario=p.get("scenario"),
    )


def _def_explanation(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    labels = p.get("labels", {})
    return make_analysis(
        kind="bn_explain",
        evidence={labels.get(k, k): v for k, v in p["evidence"].items()},
        soft={labels.get(k, k): v for k, v in (p.get("soft") or {}).items()},
        likelihood={labels.get(k, k): v for k, v in (p.get("likelihood") or {}).items()},
        over=[labels.get(n, n) for n in p["over"]] if p["kind"] == "MAP" else [],
    )


def _def_monte_carlo(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    labels = p.get("labels", {})
    return make_analysis(
        kind="bn_monte_carlo", target=labels.get(p["target"], p["target"]), state=p["focus_state"],
        evidence={labels.get(k, k): v for k, v in p["evidence"].items()},
        soft={labels.get(k, k): v for k, v in (p.get("soft") or {}).items()},
        likelihood={labels.get(k, k): v for k, v in (p.get("likelihood") or {}).items()},
        runs=p["runs"], seed=p["seed"], scenario=p.get("scenario"),
    )


def _def_compare(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    labels = p.get("labels", {})
    return make_analysis(
        kind="bn_compare", target=p["label"], state=p["focus_state"], scenarios=list(p["scenarios"]),
        evidence={labels.get(k, k): v for k, v in p["evidence"].items()},
        soft={labels.get(k, k): v for k, v in (p.get("soft") or {}).items()},
        likelihood={labels.get(k, k): v for k, v in (p.get("likelihood") or {}).items()},
        reference=p.get("reference"), runs=p["runs"], seed=p["seed"],
    )


def _def_sensitivity(p: dict[str, Any]):
    from latris.schema.build_spec import make_analysis

    labels = _relabeled(p)
    return make_analysis(
        kind="bn_sensitivity", target=labels.get(p["target_id"], p["target_id"]), state=p["target_state"],
        evidence={labels.get(k, k): v for k, v in (p.get("evidence") or {}).items()},
    )


# ── outcome of interest ──────────────────────────────────────────────


def _outcome_ids(paths) -> set[str]:
    """Factors given the ``outcome`` role before BN joined the registry (new projects are refused the role)."""
    path = paths.role_path("bn")
    if not path.exists():
        return set()
    from latris.repo.yaml_io import load_model
    from latris.schema.roles import RoleSet

    return {e.target_id for e in load_model(RoleSet, path).entries if e.value == "outcome"}


# ── interpretation (structural claims; the numbers' claims sit on the ResultKinds) ──


def _claims(paths, section: str) -> list[str]:
    from latris.operations import bn as bn_ops

    if section == "structure":
        problems = bn_ops.structure_problems(root=paths.root)
        if problems:
            return [f"The Bayesian network is incomplete: {len(problems)} structural problem(s) "
                    f"(e.g. {problems[0].message})"]
        return [f"Bayesian network: {len(bn_ops.get_cpts(root=paths.root).entries)} probability table(s), "
                "all complete and normalised, structure acyclic."]
    if section == "gaps":
        rows = [r for cpt in bn_ops.get_cpts(root=paths.root).entries for r in cpt.rows]
        unreviewed = [r for r in rows if r.verification != _REVIEWED]
        if unreviewed:
            return [f"{len(unreviewed)} of {len(rows)} probability row(s) not yet reviewed by a person."]
    return []


# ── build spec and share links ───────────────────────────────────────


def _check(block, known, outcome: str | None) -> list[str]:
    names = (
        [("bn states", s.node) for s in block.states]
        + [("bn table", t.node) for t in block.tables]
        + [("bn table", parent) for t in block.tables for parent in t.parents]
        + [("bn noisy-or", n.node) for n in block.noisy_or]
        + [("bn noisy-or cause", c.parent) for n in block.noisy_or for c in n.causes]
        + [("bn uncertainty", u.node) for u in block.uncertainty]
        + [("bn scenario", n) for sc in block.scenarios
           for n in [*sc.observe, *sc.soft, *sc.likelihood, *sc.set]]
    )
    return [f"{where}: no factor named {n!r}" for where, n in names if not known(n)]


def _apply(block, verified_by: str, root: Path) -> int:
    from latris.operations import bn as bn_ops

    origin = default_origin(verified_by)
    n = 0
    for s in block.states:
        bn_ops.set_state_space(s.node, s.states, ordered=s.ordered, root=root)
        n += 1
    for t in block.tables:
        bn_ops.set_cpt(t.node, t.parents, t.probabilities, origin=t.origin or origin,  # type: ignore[arg-type]
                       source_id=t.source, root=root)
        n += 1
    for no in block.noisy_or:
        bn_ops.set_noisy_or(no.node, no.leak, [(c.parent, c.active_state, c.probability) for c in no.causes],
                            active=no.active, origin=no.origin or origin, source_id=no.source,
                            root=root)  # type: ignore[arg-type]
        n += 1
    from latris.operations import uncertainty

    for u in block.uncertainty:
        uncertainty.set_table_uncertainty(u.node, u.n, row=u.row, reason=u.reason, source_id=u.source,
                                          origin=u.origin or origin, root=root)  # type: ignore[arg-type]
        n += 1
    from latris.operations import bn_scenarios
    from latris.operations.build import _parents_first

    def dist(block: dict[str, dict[str, float]]) -> list[str]:
        return [f"{k}=" + ",".join(f"{st}:{v:g}" for st, v in d.items()) for k, d in block.items()]

    for sc in _parents_first(block.scenarios):
        bn_scenarios.set_scenario(
            sc.name, observe=[f"{k}={v}" for k, v in sc.observe.items()], soft=dist(sc.soft),
            likelihood=dist(sc.likelihood), set_=[f"{k}={v}" for k, v in sc.set.items()], tables=sc.tables,
            extends=sc.extends, description=sc.description, reason=sc.reason,
            origin=sc.origin or origin, source_id=sc.source, root=root,  # type: ignore[arg-type]
        )
        n += 1
    return n


def _export(paths, labels: dict[str, str]):
    """Bayesian network states and tables as spec entries (flattened, first parent slowest)."""
    import itertools

    from latris.operations import bn as bn_ops
    from latris.operations import uncertainty
    from latris.schema.build_spec import (
        SpecBN,
        SpecBNStates,
        SpecBNTable,
        SpecBNUncertainty,
        SpecNoisyOr,
        SpecNoisyOrCause,
    )

    spaces = {e.target_id: e for e in bn_ops.get_state_spaces(root=paths.root).entries if e.target_id in labels}
    if not spaces:
        return None
    states = [SpecBNStates(node=labels[k], states=e.states, ordered=e.ordered) for k, e in spaces.items()]
    tables = []
    for cpt in bn_ops.get_cpts(root=paths.root).entries:
        if cpt.target_id not in labels or any(p not in spaces for p in cpt.parents):
            continue
        rows = {tuple(sorted(r.parent_states.items())): r for r in cpt.rows}
        probs: list[float] = []
        for combo in itertools.product(*(spaces[p].states for p in cpt.parents)):
            row = rows.get(tuple(sorted(zip(cpt.parents, combo, strict=True))))
            if row is None:
                break
            probs.extend(row.p)
        else:
            first = cpt.rows[0] if cpt.rows else None
            tables.append(SpecBNTable(
                node=labels[cpt.target_id], parents=[labels[p] for p in cpt.parents], probabilities=probs,
                origin=first.origin if first else None, source=first.source_id if first else None,
            ))
    noisy = [
        SpecNoisyOr(
            node=labels[e.target_id], leak=e.leak, origin=e.origin, source=e.source_id, active=e.active_state,
            causes=[SpecNoisyOrCause(parent=labels[c.parent_id], active_state=c.active_state, probability=c.prob)
                    for c in e.links if c.parent_id in labels],
        )
        for e in bn_ops.get_noisy_or(root=paths.root).entries if e.target_id in labels and e.links
    ]
    ranges = []
    for node, cells in uncertainty.bn_specs(paths).items():
        if node not in labels:
            continue
        for cell, e in cells.items():
            row = None
            if cell != uncertainty.BN_TABLE:
                pairs = [part.split("=", 1) for part in cell.split(":", 2)[-1].split(",")]
                row = ",".join(f"{labels.get(pid, pid)}={state}" for pid, state in pairs)
            ranges.append(SpecBNUncertainty(node=labels[node], n=e.params["n"], row=row, reason=e.reason,
                                            origin=e.origin, source=e.source_id))
    from latris.operations import bn_scenarios
    from latris.schema.build_spec import SpecBNScenario

    def named(block: dict) -> bool:
        return all(k in labels for k in block)

    def table_text(o) -> str:  # noqa: ANN001
        cond = ",".join(f"{labels[k]}={v}" for k, v in o.parent_states.items())
        return f"{labels[o.target_id]}{'[' + cond + ']' if cond else ''}=" + ",".join(f"{x!r}" for x in o.p)

    scenarios = [
        SpecBNScenario(
            name=s.name, extends=s.extends, description=s.description, reason=s.reason, origin=s.origin,
            source=s.source_id, observe={labels[k]: v for k, v in s.evidence.items()},
            soft={labels[k]: v for k, v in s.soft.items()}, likelihood={labels[k]: v for k, v in s.likelihood.items()},
            set={labels[k]: v for k, v in s.interventions.items()}, tables=[table_text(o) for o in s.tables],
        )
        for s in bn_scenarios.load(paths).scenarios
        if all(named(b) for b in (s.evidence, s.soft, s.likelihood, s.interventions))
        and all(o.target_id in labels and named(o.parent_states) for o in s.tables)
    ]
    return SpecBN(states=states, tables=tables, noisy_or=noisy, uncertainty=ranges, scenarios=scenarios)


# ── diagram ──────────────────────────────────────────────────────────


def _mermaid(paths, entities, edges) -> str:
    """The network with each node's states; the latest query's observed evidence and target marked.

    Numbers stay in Results — the diagram shows structure and what was observed/asked.
    """
    from latris.exporters.mermaid import _mermaid_text
    from latris.operations import bn as bn_ops
    from latris.operations.analysis_results import report_results

    spaces = {e.target_id: e.states for e in bn_ops.get_state_spaces(root=paths.root).entries}
    if not spaces:
        return ""  # no parameterisation yet — the generic sketch says as much
    evidence: dict[str, str] = {}
    targets: set[str] = set()
    for r in report_results(model_types=["bn"], root=paths.root):
        if r.run.result_kind == "bn-query" and not r.stale:
            evidence = r.payload.get("evidence") or {}
            targets = set(r.payload.get("posteriors") or {})
            break
    alias = {e.id: f"n{i}" for i, e in enumerate(entities)}
    lines = ["flowchart LR"]
    for e in entities:
        text = _mermaid_text(e.label)
        states = spaces.get(e.id)
        if states:
            text += "<br/>" + " · ".join(_mermaid_text(s) for s in states)
        if e.id in evidence:
            lines.append(f'    {alias[e.id]}(["{text}<br/>observed: {_mermaid_text(evidence[e.id])}"])')
        elif e.id in targets:
            lines.append(f'    {alias[e.id]}(("{text}"))')
        else:
            lines.append(f'    {alias[e.id]}["{text}"]')
    for e in edges:
        if e.kind == "causal":
            lines.append(f"    {alias[e.from_id]} --> {alias[e.to_id]}")
        else:
            lines.append(f'    {alias[e.from_id]} -.->|"{_mermaid_text(e.kind)}"| {alias[e.to_id]}')
    return "\n".join(lines) + "\n"


def _problems(root: Path) -> list:
    from latris.operations import bn as bn_ops

    return bn_ops.structure_problems(root=root)


register(Formalism(
    model_type="bn",
    outcome_role=None,
    outcome_refusal=("A Bayesian network has no single outcome — query the factor you care about "
                     "(latris bn query <factor> --state …) instead of giving it an 'outcome' role."),
    outcome_ids=_outcome_ids,
    structure_problems=_problems,
    validators={
        "state_space_defined": ("missing_state_space",),
        "cpt_complete": ("cpt_conflict", "missing_cpt", "cpt_incomplete", "cpt_unnormalised"),
    },
    claims=_claims,
    results=(
        ResultKind(kind="bn-query", title="Probabilities", render=_render_query, analysis="bn_query",
                   run=_run_query, definition=_def_query, claims=_claims_query, report_limit=6,
                   charts=lambda p: [("posterior", {})], chart_kinds=("posterior",), subtitle=_subtitle_given),
        ResultKind(kind="bn-explanation", title="Most likely explanation", render=_render_explanation,
                   analysis="bn_explain", run=_run_explain, definition=_def_explanation,
                   claims=_claims_explanation, subtitle=_subtitle_given),
        ResultKind(kind="bn-monte-carlo", title="How sure the probability is (Monte Carlo)",
                   render=_render_monte_carlo, analysis="bn_monte_carlo", run=_run_monte_carlo,
                   definition=_def_monte_carlo, claims=_claims_monte_carlo,
                   charts=lambda p: [("bn-interval", {})], chart_kinds=("bn-interval",), subtitle=_subtitle_target),
        ResultKind(kind="bn-options", title="Options compared", render=_render_options,
                   analysis="bn_compare", run=_run_compare, definition=_def_compare, claims=_claims_options,
                   subtitle=lambda p: f"P({p['label']} = {p['focus_state']})"
                   + (f" given {_given(p)}" if _given(p) else "")),
        ResultKind(kind="bn-sensitivity", title="Probability sensitivity", render=_render_sensitivity,
                   analysis="bn_sensitivity", run=_run_sensitivity, definition=_def_sensitivity,
                   claims=_claims_sensitivity, charts=lambda p: [("bn-tornado", {})], chart_kinds=("bn-tornado",),
                   subtitle=_subtitle_target),
    ),
    spec_field="bn",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    mermaid=_mermaid,
    cli=("latris.cli.bn_cmd", "bn"),
    routes="latris.server.routes.bn",
))
