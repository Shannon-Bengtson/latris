"""SD loop dominance — which feedback loop drives behaviour, and when (Loops That Matter).

Implements the Loops That Matter method (Schoenberg, Davidsen & Eberlein,
SDR 2020) with the revised flow-to-stock link score (Schoenberg, Hayward &
Eberlein, SDR 2023), the approach Stella and pysimlin ship.

The loop graph comes from the *compiled model*, not the diagram: feedback
through a stock (stock → outflow → stock) is not a cycle in the substrate,
because a flow edge runs stock → flow → sink. Its edges are:

- information links: every stock or computed variable an equation reads;
- flow-to-stock links: each inflow (+) and outflow (−) to its stock.

Link scores at each step (one ``dt``; everything else held at the previous step):

- information link x → z:  ``|Δₓz / Δz| · sign(Δₓz / Δx)`` where Δₓz is the
  change in z from x alone (z re-evaluated with x now, its other inputs then);
- flow f → stock S:  ``|Δf / Δnet(S)| · (±1)``, Δnet the change in the
  stock's net flow — the 2023 revision, which makes scores independent of how
  flows are split or merged.

A loop's score is the product of its link scores; its *relative* score is that
divided by the sum of |scores| of the loops it interacts with (those sharing a
variable). A loop, or the smallest set of loops, holding at least 50% of the
relative score dominates. Scores are zero at the first step and whenever the
stocks stop changing — the method explains change, not equilibrium.

Loops are enumerated exhaustively (Johnson's algorithm) up to a cap; very
large models would need the strongest-path search, not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from latris.operations.graph_analysis import TooManyLoops, find_all_loops
from latris.operations.sd_inference import SDModel, fast_model, simulate, with_values
from latris.operations.sd_scenarios import _r, _thin, apply_overrides
from latris.schema.sd import SDScenario

MAX_LOOPS = 500
MAX_PERIODS_DESCRIBED = 4  # the summary names the longest dominant periods; the table and chart have them all
DOMINANT_SHARE = 0.5


@dataclass(frozen=True)
class _Link:
    id: str
    from_id: str
    to_id: str
    kind: str  # "info" | "flow"
    sign: int = 1  # flow links: +1 inflow, −1 outflow


def loop_links(model: SDModel) -> list[_Link]:
    by_slug = {s: i for i, s in model.slugs.items()}
    dynamic = {*model.stocks, *model.order}
    links: list[_Link] = []
    for z in model.order:
        for name in sorted(model.equations[z].names):
            x = by_slug.get(name)
            if x in dynamic:
                links.append(_Link(f"{x}>{z}", x, z, "info"))
    for s in model.stocks:
        for f in model.inflows.get(s, []):
            links.append(_Link(f"{f}>{s}", f, s, "flow", +1))
        for f in model.outflows.get(s, []):
            links.append(_Link(f"{f}>{s}", f, s, "flow", -1))
    return links


def _sign(x: float) -> float:
    return (x > 0) - (x < 0)


def _components(loops: list[tuple[str, ...]]) -> list[int]:
    """Interacting loop sets: loops sharing any variable are in the same set."""
    parent = list(range(len(loops)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for i, nodes in enumerate(loops):
        for n in nodes:
            if n in owner:
                parent[find(i)] = find(owner[n])
            else:
                owner[n] = i
    roots: dict[int, int] = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(len(loops))]


def loop_dominance(
    model: SDModel,
    *,
    scenario: SDScenario | None = None,
    edge_lookup: dict[tuple[str, str], str] | None = None,
    edge_info: dict[str, dict[str, Any]] | None = None,
    start: float | None = None,
    end: float | None = None,
    max_loops: int = MAX_LOOPS,
) -> dict[str, Any]:
    """Score every feedback loop over a simulation and find when each one dominates."""
    base = apply_overrides(model, scenario.overrides) if scenario else model
    fast = fast_model(base)
    if fast is None:
        raise ValueError("loop dominance needs every unit to be multiplicative (no degC/degF offsets) in this version")
    links = loop_links(base)
    try:
        raw_loops = find_all_loops(links, max_loops=max_loops)
    except TooManyLoops as exc:
        raise ValueError(
            f"this model has {exc} — too many to score one by one; loop dominance currently handles models "
            f"with up to {max_loops} feedback loops"
        ) from exc

    fine = with_values(base, settings=base.settings.model_copy(update={"saveper": None}))
    res = simulate(fine, include_hidden=True)  # SMOOTH/DELAY structure carries feedback too
    if not res.success:
        raise ValueError(f"the simulation failed, so its loops can't be scored: {res.message}")
    times = res.times
    n = len(times)
    lo = times[0] if start is None else start
    hi = times[-1] if end is None else end
    if lo >= hi:
        raise ValueError("the analysis window must have --from before --to")

    # Every variable in SI base magnitudes (the fast path's representation).
    base_vals: dict[str, list[float]] = {}
    for s in base.stocks:
        f = fast.stock_factor[s]
        base_vals[s] = [x * f for x in res.series[s]]
    for v in base.order:
        f = fast.out_factor[v]
        base_vals[v] = [x * f for x in res.series[v]]
    consts = dict(zip(fast.const_ids, fast.constants_vector(base), strict=True))
    const_env = {base.slugs[c]: val for c, val in consts.items()}
    tf = fast.time_factor

    link_by_id = {lk.id: lk for lk in links}
    used = {eid for loop in raw_loops for eid in loop.edge_ids}
    scores: dict[str, list[float]] = {}
    net: dict[str, list[float]] = {}
    for s in base.stocks:
        ins = [base_vals[f] for f in base.inflows.get(s, [])]
        outs = [base_vals[f] for f in base.outflows.get(s, [])]
        net[s] = [sum(c[t] for c in ins) - sum(c[t] for c in outs) for t in range(n)]

    for eid in used:
        lk = link_by_id[eid]
        x, z = lk.from_id, lk.to_id
        out = [0.0] * n
        if lk.kind == "flow":
            for t in range(1, n):
                d_net = net[z][t] - net[z][t - 1]
                if d_net != 0:
                    out[t] = abs((base_vals[x][t] - base_vals[x][t - 1]) / d_net) * lk.sign
        else:
            eq = fast.equation[z]
            for t in range(1, n):
                dz = base_vals[z][t] - base_vals[z][t - 1]
                dx = base_vals[x][t] - base_vals[x][t - 1]
                if dz == 0 or dx == 0:
                    continue
                env = dict(const_env)
                for v, series in base_vals.items():
                    env[base.slugs[v]] = series[t - 1]
                env[base.slugs[x]] = base_vals[x][t]
                dxz = eq(times[t - 1] * tf, env) - base_vals[z][t - 1]
                out[t] = abs(dxz / dz) * _sign(dxz / dx)
        scores[eid] = out

    node_lists = [loop.node_ids for loop in raw_loops]
    loop_scores = []
    for loop in raw_loops:
        series = [0.0] * n
        for t in range(1, n):
            p = 1.0
            for eid in loop.edge_ids:
                p *= scores[eid][t]
            series[t] = p
        loop_scores.append(series)
    sets = _components(node_lists)
    relative: list[list[float]] = [[0.0] * n for _ in raw_loops]
    for k in set(sets):
        members = [i for i, s in enumerate(sets) if s == k]
        for t in range(n):
            total = sum(abs(loop_scores[i][t]) for i in members)
            if total > 0:
                for i in members:
                    relative[i][t] = loop_scores[i][t] / total

    window = [t for t in range(1, n) if lo <= times[t] <= hi]
    if not window:
        raise ValueError(f"no simulated steps between {lo:g} and {hi:g}")

    # Name loops R1, R2, B1 … by runtime polarity, most influential first.
    stats = []
    for i in range(len(raw_loops)):
        share = sum(abs(relative[i][t]) for t in window) / len(window)
        signed = sum(relative[i][t] for t in window)
        signs = {_sign(relative[i][t]) for t in window if abs(relative[i][t]) > 1e-9}
        stats.append((i, share, "R" if signed >= 0 else "B", len(signs) > 1))
    labels: dict[int, str] = {}
    for pol in ("R", "B"):
        ranked = sorted((s for s in stats if s[2] == pol), key=lambda s: -s[1])
        for rank, (i, *_rest) in enumerate(ranked, start=1):
            labels[i] = f"{pol}{rank}"

    edge_lookup = edge_lookup or {}
    edge_info = edge_info or {}
    idx = _thin(n)
    loops_out = []
    for i, share, pol, flips in sorted(stats, key=lambda s: -s[1]):
        loop = raw_loops[i]
        # Read each loop from a stock (by label), e.g. "Water → Outflow", not from the smallest id.
        nodes, edges = list(loop.node_ids), list(loop.edge_ids)
        stocks_in = sorted(
            (k for k, nd in enumerate(nodes) if nd in base.stock_units), key=lambda k: base.labels[nodes[k]]
        )
        k0 = stocks_in[0] if stocks_in else 0
        members, loop_edges = nodes[k0:] + nodes[:k0], edges[k0:] + edges[:k0]
        link_rows, weak = [], []
        for eid in loop_edges:
            lk = link_by_id[eid]
            sub = edge_lookup.get((lk.from_id, lk.to_id)) or (
                edge_lookup.get((lk.to_id, lk.from_id)) if lk.kind == "flow" or lk.from_id in base.stocks else None
            )
            info = edge_info.get(sub or "", {})
            text = f"{base.labels[lk.from_id]} → {base.labels[lk.to_id]}"
            link_rows.append(
                {"from": base.labels[lk.from_id], "to": base.labels[lk.to_id], "kind": lk.kind, "edge_id": sub}
            )
            if lk.kind == "info":  # flow-to-stock links are accounting, true by definition
                reasons = []
                if info.get("against"):
                    reasons.append("evidence against it")
                if not info.get("sources") and info.get("confidence") not in ("high", "by-definition"):
                    reasons.append("no source")
                if info.get("confidence") == "low":
                    reasons.append("low confidence")
                if reasons:
                    weak.append({"link": text, "edge_id": sub, "why": ", ".join(reasons)})
        loops_out.append(
            {
                "id": labels[i],
                "polarity": pol,
                "polarity_changes": flips,
                "members": [base.labels[m] for m in members],
                "member_ids": members,
                "links": link_rows,
                "set": sets[i],
                "average_share": _r(share),
                "relative_score": [_r(relative[i][t]) for t in idx],
                "weak_links": weak,
            }
        )

    sets_out = []
    for k in sorted(set(sets)):
        members = [i for i, s in enumerate(sets) if s == k]
        periods: list[dict[str, Any]] = []
        for t in window:
            ranked = sorted(members, key=lambda i: -abs(relative[i][t]))
            chosen, cum = [], 0.0
            for i in ranked:
                if abs(relative[i][t]) <= 1e-12:
                    break
                chosen.append(i)
                cum += abs(relative[i][t])
                if cum >= DOMINANT_SHARE:
                    break
            key = tuple(sorted(labels[i] for i in chosen)) if cum >= DOMINANT_SHARE else ()
            if periods and tuple(periods[-1]["loops"]) == key:
                periods[-1]["end"] = times[t]
                periods[-1]["_shares"].append(cum)
            else:
                periods.append({"start": times[t - 1], "end": times[t], "loops": list(key), "_shares": [cum]})
        for p in periods:
            shares = p.pop("_shares")
            p["share"] = _r(sum(shares) / len(shares)) if p["loops"] else 0.0
            p["start"], p["end"] = _r(p["start"]), _r(p["end"])
        sets_out.append({"id": k, "loops": [labels[i] for i in members], "dominant_periods": periods})

    return {
        "times": [_r(times[t]) for t in idx],
        "time_units": res.time_units,
        "window": [_r(lo), _r(hi)],
        "scenario": scenario.name if scenario else None,
        "loops": loops_out,
        "sets": sets_out,
        "variables": len(base.stocks) + len(base.order),
        "links": len(links),
        "method": res.method,
        "algorithm": res.algorithm,
        "settings": res.settings,
        "notes": [] if raw_loops else ["The model has no feedback loops: every effect runs one way."],
    }


def describe(payload: dict[str, Any]) -> str:
    """'B1 (PM2.5 Load → Dispersal) dominates 0–2.1 years (82%); then R1 …'."""
    if not payload["loops"]:
        return "No feedback loops."
    by_id = {lp["id"]: lp for lp in payload["loops"]}

    def name(lid: str) -> str:
        members = by_id[lid]["members"]
        shown = " → ".join(members[:3]) + (" → …" if len(members) > 3 else "")
        return f"{lid} ({shown})"

    periods = [p for s in payload["sets"] for p in s["dominant_periods"] if p["loops"]]
    if not periods:
        return "No loop dominates (the stocks barely change)."
    shown = periods
    if len(periods) > MAX_PERIODS_DESCRIBED:
        longest = sorted(periods, key=lambda p: p["end"] - p["start"], reverse=True)[:MAX_PERIODS_DESCRIBED]
        shown = sorted(longest, key=lambda p: p["start"])
    parts = [
        f"{' + '.join(name(lid) for lid in p['loops'])} dominates {p['start']:g}–{p['end']:g} "
        f"{payload['time_units']} ({p['share'] * 100:.0f}%)"
        for p in shown
    ]
    rest = len(periods) - len(shown)
    return "; then ".join(parts) + (f" (+{rest} shorter switch{'es' if rest != 1 else ''})" if rest else "")
