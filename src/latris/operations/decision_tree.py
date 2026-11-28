"""Decision trees — the best choice under uncertainty, and what more information is worth.

The decision tree of decision analysis (Raiffa 1968; Clemen & Reilly 2014):
**decision** nodes where someone chooses, **chance** nodes where the world
does (each branch with a probability), and **terminal** nodes with a payoff.
Values incurred along a branch (the cost of a test) add to whatever follows.

The analysis **rolls back** the tree — a chance node is worth the
probability-weighted value of its branches, a decision node the best of its
— to give the optimal strategy and the expected value of each first choice.
Then:

- **Expected value of perfect information** (EVPI) for each uncertainty:
  how much better the decision would be if the uncertainty were known before
  choosing — the most it's worth paying to find out. Chance nodes that are
  the same uncertainty under different choices (the market's demand whether
  you launch or license) are grouped by name, and must give it the same
  probabilities: otherwise the uncertainty depends on the choice and perfect
  information about it isn't defined.
- **Probability thresholds**: for each two-state uncertainty, how far its
  probability would have to move before the best first choice changes.
- the values on the optimal path nobody has verified.

Nodes are substrate entities with a ``decision_tree`` role; branches are
ordinary edges; the numbers are stored with provenance
(``schema/decision_tree.py``).
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from latris.operations._resolve import resolve_target
from latris.operations._view_store import ViewStore, replace_entry, resolve_factor
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model
from latris.schema import Substrate
from latris.schema.common import ProvenanceOrigin, ProvenanceVerification
from latris.schema.decision_tree import (
    DT_ELEMENTS,
    DTBranchEntry,
    DTBranchSet,
    DTChanceEntry,
    DTChanceSet,
    DTPayoffEntry,
    DTPayoffSet,
    DTSettings,
)

MODEL_TYPE = "decision_tree"
MAX_JOINT_STATES = 4096
_UNSET = object()
_TOL = 1e-6


_store = ViewStore(MODEL_TYPE, DT_ELEMENTS)


def get_elements(*, root: Path | None = None) -> dict[str, str]:
    return _store.roles(root)


def get_branches(*, root: Path | None = None) -> DTBranchSet:
    return _store.load(root, "branch", DTBranchSet)


def get_payoffs(*, root: Path | None = None) -> DTPayoffSet:
    return _store.load(root, "payoff", DTPayoffSet)


def get_chances(*, root: Path | None = None) -> DTChanceSet:
    return _store.load(root, "chance", DTChanceSet)


def get_settings(*, root: Path | None = None) -> DTSettings:
    return _store.load(root, "settings", DTSettings)


# ── writes ───────────────────────────────────────────────────────────


def _substrate(paths) -> Substrate:
    return load_model(Substrate, paths.conceptual_yaml)


def _node(paths, target: str, element: str | None = None) -> tuple[str, str]:
    tid, label = resolve_factor(paths, target, link_error=f"{target!r} is a link, not a node")
    if element:
        got = get_elements(root=paths.root).get(tid)
        if got != element:
            raise ValueError(f"{label} is {('a ' + got + ' node') if got else 'not in the decision tree'}, not a "
                             f"{element} node (`latris dt element <factor> {element}`)")
    return tid, label


def set_element(target: str, element: str, *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.view_roles import set_role

    if element not in DT_ELEMENTS:
        raise ValueError(f"{element!r} is not a decision-tree node type. Types: {', '.join(DT_ELEMENTS)}")
    return set_role(target, MODEL_TYPE, element, root=root)


def set_branch(
    edge: str,
    *,
    label: str | None | object = _UNSET,
    probability: float | None | object = _UNSET,
    value: float | object = _UNSET,
    notes: str | None | object = _UNSET,
    origin: ProvenanceOrigin | object = _UNSET,
    source_id: str | None | object = _UNSET,
    verification: ProvenanceVerification | object = _UNSET,
    root: Path | None = None,
) -> tuple[DTBranchEntry, str]:
    """Set a branch's label, probability (chance branches), value along it, or provenance; only what's given changes."""
    paths = require_project(root)
    sub = _substrate(paths)
    eid = resolve_target(edge, sub)
    e = next((x for x in sub.edges if x.id == eid), None)
    if e is None:
        raise ValueError(f"{edge!r} is a node; a branch is a link, written 'Parent -> Child'")
    el = get_elements(root=paths.root)
    if el.get(e.from_id) not in ("decision", "chance") or e.to_id not in el:
        raise ValueError("a branch runs from a decision or chance node to another decision-tree node")
    if probability is not _UNSET and probability is not None and el[e.from_id] != "chance":
        raise ValueError("only branches from a chance node take a probability")
    store = get_branches(root=paths.root)
    current = next((b for b in store.entries if b.target_id == eid), None)
    given = {"label": label, "probability": probability, "value": value, "notes": notes, "origin": origin,
             "source_id": source_id, "verification": verification}
    changed = {k: v for k, v in given.items() if v is not _UNSET}
    if not changed:
        raise ValueError("nothing to set: give a label, probability, value, notes or source")
    entry = DTBranchEntry.model_validate({**(current.model_dump() if current else {"target_id": eid}), **changed})
    replace_entry(store, entry)
    labels = {x.id: x.label for x in sub.entities}
    sha = _store.save(paths, "branch", store,
        subject=f"Set decision-tree branch {labels[e.from_id]} → {labels[e.to_id]}: "
            f"{', '.join(changed)}",
        body=f"edge: {eid}\n" + "\n".join(f"{k}: {v}" for k, v in changed.items()))
    return entry, sha


def set_payoff(
    target: str,
    value: float,
    *,
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    verification: ProvenanceVerification = "unverified",
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[DTPayoffEntry, str]:
    paths = require_project(root)
    tid, label = _node(paths, target, "terminal")
    entry = DTPayoffEntry(target_id=tid, value=value, origin=origin, source_id=source_id, verification=verification,
                          notes=notes)
    store = get_payoffs(root=paths.root)
    replace_entry(store, entry)
    sha = _store.save(paths, "payoff", store, subject=f"Set decision-tree payoff {label} = {value:g}",
        body=f"target: {tid}\nvalue: {value}\norigin: {origin}\nsource_id: {source_id}")
    return entry, sha


def set_uncertainty(target: str, name: str, *, root: Path | None = None) -> tuple[DTChanceEntry, str]:
    """Name the uncertainty a chance node resolves; chance nodes with the same name are priced together."""
    paths = require_project(root)
    tid, label = _node(paths, target, "chance")
    if not name.strip():
        raise ValueError("give the uncertainty a name")
    entry = DTChanceEntry(target_id=tid, uncertainty=name.strip())
    store = get_chances(root=paths.root)
    replace_entry(store, entry)
    sha = _store.save(paths, "chance", store, subject=f"Decision-tree chance node {label} resolves {entry.uncertainty}",
        body=f"target: {tid}\nuncertainty: {entry.uncertainty}")
    return entry, sha


def set_settings(*, objective: str | None = None, units: str | None = None,
                 root: Path | None = None) -> tuple[DTSettings, str]:
    paths = require_project(root)
    s = get_settings(root=paths.root)
    data = s.model_dump()
    if objective is not None:
        data["objective"] = objective
    if units is not None:
        data["units"] = units or None
    s = DTSettings.model_validate(data)
    sha = _store.save(paths, "settings", s, subject=f"Decision-tree settings: {s.objective}"
            + (f", {s.units}" if s.units else ""), body="")
    return s, sha


# ── structure ────────────────────────────────────────────────────────


@dataclass
class DTProblem:
    target_id: str | None
    gap_type: str
    message: str


@dataclass
class Tree:
    labels: dict[str, str]
    kind: dict[str, str]
    children: dict[str, list[tuple[str, str]]]  # node → [(edge, child)]
    branches: dict[str, DTBranchEntry]
    payoffs: dict[str, DTPayoffEntry]
    uncertainty: dict[str, str]  # chance node → uncertainty name
    settings: DTSettings
    root: str | None
    problems: list[DTProblem] = field(default_factory=list)

    @property
    def sign(self) -> float:
        return 1.0 if self.settings.objective == "maximise" else -1.0

    def branch_label(self, edge: str, child: str) -> str:
        b = self.branches.get(edge)
        return b.label if b and b.label else self.labels[child]


def _root_problems(kind: dict[str, str], roots: list[str], parents: dict[str, int]) -> list[DTProblem]:
    """One root, one parent per node, and a decision to make."""
    problems: list[DTProblem] = []
    if not kind:
        problems.append(DTProblem(None, "dt_no_root", "No nodes yet: give factors a decision-tree type."))
    elif not roots:
        problems.append(DTProblem(None, "dt_no_root", "Every node has a parent: the tree has no root (it loops)."))
    elif len(roots) > 1:
        problems.append(DTProblem(roots[1], "dt_many_roots", "More than one node has no parent; a tree has one root."))
    for n, c in parents.items():
        if c > 1:
            problems.append(DTProblem(n, "dt_not_tree", "More than one branch leads here; in a tree each node has one "
                                                        "parent (repeat the node under each branch instead)."))
    if "decision" not in kind.values() and kind:
        problems.append(DTProblem(None, "dt_no_decision", "No decision node: say what is being chosen."))
    return problems


def _has_cycle(kind: dict[str, str], children: dict[str, list[tuple[str, str]]]) -> bool:
    state: dict[str, int] = {}

    def cyc(n: str) -> bool:
        state[n] = 1
        for _, c in children.get(n, []):
            if state.get(c) == 1 or (c not in state and cyc(c)):
                return True
        state[n] = 2
        return False

    return any(n not in state and cyc(n) for n in kind)


def _chance_problem(t: Tree, n: str, kids: list[tuple[str, str]]) -> DTProblem | None:
    """Every branch from a chance node has a probability, and they sum to 1."""
    probs: list[float] = []
    for e, _ in kids:
        b = t.branches.get(e)
        if b is None or b.probability is None:
            return DTProblem(n, "dt_no_probability", "Every branch from a chance node needs a probability.")
        probs.append(b.probability)
    if abs(sum(probs) - 1) > _TOL:
        return DTProblem(n, "dt_probabilities_sum", f"Branch probabilities sum to {sum(probs):.4g}, not 1.")
    return None


def _node_problems(t: Tree) -> list[DTProblem]:
    """What each node needs for its type: branches, a payoff, probabilities."""
    problems: list[DTProblem] = []
    for n, k in t.kind.items():
        kids = t.children.get(n, [])
        if k in ("decision", "chance") and not kids:
            problems.append(DTProblem(n, "dt_dead_end", f"A {k} node needs branches."))
        if k == "terminal" and kids:
            problems.append(DTProblem(n, "dt_terminal_has_children", "A terminal node ends a path; make it a "
                                                                     "decision or chance node to branch on."))
        if k == "terminal" and n not in t.payoffs:
            problems.append(DTProblem(n, "dt_no_payoff", "No payoff (`latris dt payoff`)."))
        if k == "chance" and kids and (p := _chance_problem(t, n, kids)):
            problems.append(p)
    return problems


def load_tree(*, root: Path | None = None) -> Tree:
    paths = require_project(root)
    sub = _substrate(paths)
    labels = {e.id: e.label for e in sub.entities}
    kind = {k: v for k, v in get_elements(root=paths.root).items() if k in labels}
    children: dict[str, list[tuple[str, str]]] = defaultdict(list)
    parents: dict[str, int] = defaultdict(int)
    for e in sub.edges:
        if e.from_id in kind and e.to_id in kind:
            children[e.from_id].append((e.id, e.to_id))
            parents[e.to_id] += 1
    for k in children:
        children[k].sort(key=lambda ec: labels[ec[1]])
    unc = {c.target_id: c.uncertainty for c in get_chances(root=paths.root).entries
           if kind.get(c.target_id) == "chance"}
    t = Tree(labels=labels, kind=kind, children=dict(children),
             branches={b.target_id: b for b in get_branches(root=paths.root).entries},
             payoffs={x.target_id: x for x in get_payoffs(root=paths.root).entries if x.target_id in kind},
             uncertainty={n: unc.get(n, labels[n]) for n, k in kind.items() if k == "chance"},
             settings=get_settings(root=paths.root), root=None)
    roots = sorted((n for n in kind if parents[n] == 0), key=lambda n: labels[n])
    t.problems += _root_problems(kind, roots, parents)
    cycle = _has_cycle(kind, t.children)
    if cycle:
        t.problems.append(DTProblem(None, "dt_cycle", "The branches loop back."))
    t.problems += _node_problems(t)
    if len(roots) == 1 and not cycle:
        t.root = roots[0]
    return t


def structure_problems(*, root: Path | None = None) -> list[DTProblem]:
    return load_tree(root=root).problems


# ── rollback ─────────────────────────────────────────────────────────


def rollback(t: Tree, forced: dict[str, str] | None = None,
             prob: dict[str, float] | None = None) -> tuple[dict[str, float], dict[str, str]]:
    """Expected value of every node and the chosen branch at every decision node.

    ``forced`` fixes uncertainties to a state (perfect information); ``prob`` overrides branch probabilities.
    """
    forced = forced or {}
    prob = prob or {}
    ev: dict[str, float] = {}
    choice: dict[str, str] = {}

    def val(n: str) -> float:
        if n in ev:
            return ev[n]
        k = t.kind[n]
        if k == "terminal":
            ev[n] = t.payoffs[n].value
            return ev[n]
        kids = t.children[n]
        along = {e: (t.branches[e].value if e in t.branches else 0.0) + val(c) for e, c in kids}
        if k == "decision":
            best = max(kids, key=lambda ec: (t.sign * along[ec[0]], -kids.index(ec)))
            choice[n] = best[0]
            ev[n] = along[best[0]]
        else:
            u = t.uncertainty[n]
            if u in forced:
                hit = [e for e, c in kids if t.branch_label(e, c) == forced[u]]
                if not hit:
                    raise ValueError(f"{t.labels[n]} has no branch for {u} = {forced[u]}")
                ev[n] = along[hit[0]]
            else:
                ev[n] = sum((prob.get(e, t.branches[e].probability or 0.0)) * along[e] for e, _ in kids)
        return ev[n]

    if t.root is None:
        raise ValueError("the tree has no root to roll back from")
    val(t.root)
    return ev, choice


def _groups(t: Tree) -> tuple[dict[str, dict[str, float]], dict[str, list[str]], list[str]]:
    """Uncertainties with consistent states and probabilities: (states → p, nodes), and why others are skipped."""
    nodes: dict[str, list[str]] = defaultdict(list)
    for n, u in t.uncertainty.items():
        nodes[u].append(n)
    ok: dict[str, dict[str, float]] = {}
    skipped: list[str] = []
    for u, ns in sorted(nodes.items()):
        dists = [{t.branch_label(e, c): t.branches[e].probability or 0.0 for e, c in t.children[n]} for n in ns]
        first = dists[0]
        if all(set(d) == set(first) and all(abs(d[s] - first[s]) < _TOL for s in first) for d in dists[1:]):
            ok[u] = first
        else:
            skipped.append(f"{u}: its states or probabilities differ between choices, so it depends on the choice "
                           "and perfect information about it isn't defined")
    return ok, {u: nodes[u] for u in ok}, skipped


def _first_choice(t: Tree, choice: dict[str, str]) -> str | None:
    if t.root is None or t.kind[t.root] != "decision":
        return None
    e = choice[t.root]
    return t.branch_label(e, dict(t.children[t.root])[e])


def evpi(t: Tree) -> dict[str, Any]:
    base_ev, base_choice = rollback(t)
    ev0 = base_ev[t.root]  # type: ignore[index]
    groups, _, skipped = _groups(t)
    out = []
    for u, states in groups.items():
        by_state = {}
        total = 0.0
        for s, p in states.items():
            ev_s, ch_s = rollback(t, forced={u: s})
            by_state[s] = {"p": p, "ev": ev_s[t.root], "choice": _first_choice(t, ch_s)}  # type: ignore[index]
            total += p * ev_s[t.root]  # type: ignore[index]
        out.append({"uncertainty": u, "states": states, "value_with_information": total,
                    "evpi": max(0.0, t.sign * (total - ev0)), "by_state": by_state})
    joint = None
    if len(groups) > 1:
        combos = 1
        for st in groups.values():
            combos *= len(st)
        if combos <= MAX_JOINT_STATES:
            total = 0.0
            names = list(groups)
            for combo in itertools.product(*(list(groups[u].items()) for u in names)):
                p = 1.0
                for _, q in combo:
                    p *= q
                if p == 0:
                    continue
                ev_c, _ = rollback(t, forced={u: s for u, (s, _) in zip(names, combo, strict=True)})
                total += p * ev_c[t.root]  # type: ignore[index]
            joint = {"value_with_information": total, "evpi": max(0.0, t.sign * (total - ev0))}
        else:
            skipped.append(f"perfect information on everything: more than {MAX_JOINT_STATES} combinations")
    return {"per_uncertainty": out, "all": joint, "skipped": skipped, "base_choice": _first_choice(t, base_choice)}


def _best_with(t: Tree, edge_pairs: list[tuple[str, str]], q: float) -> str | None:
    """The best first choice when every (first-state edge, second-state edge) pair has P = q, 1 - q."""
    prob: dict[str, float] = {}
    for e1, e2 in edge_pairs:
        prob[e1], prob[e2] = q, 1 - q
    return _first_choice(t, rollback(t, prob=prob)[1])


def _crossing(t: Tree, edge_pairs: list[tuple[str, str]], p0: float, end: float) -> tuple[float, str | None] | None:
    """Walk the probability from ``p0`` towards ``end``; at the first change of best choice, bisect to it."""
    here = _best_with(t, edge_pairs, p0)
    prev = p0
    for k in range(1, 201):
        q = p0 + (end - p0) * k / 200
        if _best_with(t, edge_pairs, q) != here:
            a, b = prev, q  # best at a is still `here`; at b it isn't
            for _ in range(40):
                m = (a + b) / 2
                a, b = (m, b) if _best_with(t, edge_pairs, m) == here else (a, m)
            return b, _best_with(t, edge_pairs, b)
        prev = q
    return None


def thresholds(t: Tree) -> list[dict[str, Any]]:
    """For each two-state uncertainty, the nearest probabilities at which the best first choice changes."""
    if t.root is None or t.kind[t.root] != "decision":
        return []
    groups, nodes, _ = _groups(t)
    out = []
    for u, states in groups.items():
        if len(states) != 2:
            continue
        s1, s2 = list(states)
        pairs = []
        for n in nodes[u]:
            by_label = {t.branch_label(e, c): e for e, c in t.children[n]}
            pairs.append((by_label[s1], by_label[s2]))
        p0 = states[s1]
        up, down = _crossing(t, pairs, p0, 1.0), _crossing(t, pairs, p0, 0.0)
        out.append({"uncertainty": u, "state": s1, "p": p0, "best": _best_with(t, pairs, p0),
                    "up": {"p": up[0], "option": up[1]} if up else None,
                    "down": {"p": down[0], "option": down[1]} if down else None})
    return out




def analyse(*, root: Path | None = None) -> dict[str, Any]:
    t = load_tree(root=root)
    lab = t.labels
    payload: dict[str, Any] = {
        "objective": t.settings.objective, "units": t.settings.units,
        "problems": [{"label": lab.get(p.target_id or "", "(tree)"), "gap_type": p.gap_type, "message": p.message}
                     for p in t.problems],
    }
    if t.problems or t.root is None:
        return payload
    ev, choice = rollback(t)
    rt = t.root
    payload["root"] = lab[rt]
    payload["ev"] = ev[rt]
    if t.kind[rt] == "decision":
        opts = []
        for e, c in t.children[rt]:
            v = (t.branches[e].value if e in t.branches else 0.0) + ev[c]
            opts.append({"option": t.branch_label(e, c), "ev": v, "best": e == choice[rt]})
        payload["options"] = sorted(opts, key=lambda o: -t.sign * o["ev"])
        payload["best"] = next(o["option"] for o in opts if o["best"])
    # The optimal strategy: every decision reached when following the best choices.
    strategy, weak = [], []
    stack = [rt]
    while stack:
        n = stack.pop()
        k = t.kind[n]
        if k == "terminal":
            if t.payoffs[n].is_weak:
                weak.append(f"payoff of {lab[n]}")
            continue
        kids = t.children[n]
        if k == "decision":
            e = choice[n]
            c = dict(kids)[e]
            strategy.append({"decision": lab[n], "choose": t.branch_label(e, c), "ev": ev[n]})
            stack.append(c)
        else:
            for e, c in kids:
                b = t.branches[e]
                if b.is_weak:
                    weak.append(f"P({t.uncertainty[n]} = {t.branch_label(e, c)})")
                stack.append(c)
    payload["strategy"] = strategy
    payload["unverified_on_path"] = sorted(set(weak))
    payload["evpi"] = evpi(t)
    payload["thresholds"] = thresholds(t)

    def node(n: str) -> dict[str, Any]:
        d: dict[str, Any] = {"node": lab[n], "type": t.kind[n], "ev": ev.get(n)}
        if t.kind[n] == "terminal":
            d["payoff"] = t.payoffs[n].value
        else:
            d["branches"] = [{"label": t.branch_label(e, c), "probability": t.branches[e].probability
                              if e in t.branches else None, "value": t.branches[e].value if e in t.branches else 0.0,
                              "chosen": choice.get(n) == e, "to": node(c)} for e, c in t.children[n]]
        return d

    payload["tree"] = node(rt)  # type: ignore[arg-type]
    return payload


def fmt(x: float, units: str | None) -> str:
    return f"{x:,.4g}" + (f" {units}" if units else "")


def describe(p: dict[str, Any]) -> str:
    if p["problems"]:
        return f"The decision tree is incomplete ({len(p['problems'])} structure problem(s))"
    u = p["units"]
    parts = []
    if p.get("best"):
        parts.append(f"Best first choice: {p['best']} (expected {fmt(p['ev'], u)})")
        if len(p["options"]) > 1:
            other = p["options"][1]
            parts.append(f"next {other['option']} ({fmt(other['ev'], u)})")
    else:
        parts.append(f"Expected value {fmt(p['ev'], u)}")
    top = max(p["evpi"]["per_uncertainty"], key=lambda x: x["evpi"], default=None)
    if top and top["evpi"] > 0:
        parts.append(f"perfect information on {top['uncertainty']} is worth up to {fmt(top['evpi'], u)}")
    elif p["evpi"]["per_uncertainty"]:
        parts.append("no single uncertainty would change the choice")
    return "; ".join(parts)


def record(payload: dict[str, Any], *, root: Path | None = None) -> tuple[str, str]:
    from latris.operations.analysis_results import record_result

    sha, run = record_result(
        kind="dt-analysis",
        key="dt-analysis",
        payload=payload,
        purpose="inference",
        algorithm="decision-tree rollback (expected value); EVPI by forcing each uncertainty; one-way probability "
                  "thresholds by bisection",
        library_version="latris",
        summary=describe(payload),
        model_type=MODEL_TYPE,
        metrics={"ev": payload.get("ev"), "best": payload.get("best"),
                 "evpi_all": (payload.get("evpi", {}).get("all") or {}).get("evpi")},
        commit_subject="Analysis: decision tree",
        root=root,
    )
    return sha, run.id
