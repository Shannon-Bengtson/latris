"""BN scenarios — named what-ifs over a Bayesian network, saved with the model, never mutating it.

A scenario holds what defines a situation or an option:

- **observations** (hard, soft or likelihood evidence): "a hot week";
- **interventions**: factors SET to a state (the do-operator): "we close the intake";
- **table overrides**: new probabilities for some rows of a table: "with the barrier upgraded,
  P(Bloom reaches intake | Barrier = upgraded) is 0.1".

The model's own tables stay as they are, so testing a barrier upgrade is a scenario, not an edit to
revert. A scenario can ``extend`` another (its changes apply first, this one's on top). Scenarios
live in ``views/parameters/bn-scenarios.yaml`` with their provenance.

Text forms (CLI, chat connector, build specs), with factor labels:

- observe / set: ``"Hot week=yes"``;
- soft / likelihood: ``"Hot week=yes:0.8"`` or ``"Hot week=yes:0.6,no:0.4"``;
- table: ``"Bloom[Barrier=upgraded]=0.1,0.9"`` (rows whose parents are in those states; a subset of
  the parents selects every matching row) or ``"Bloom=0.1,0.9"`` (every row, or a root's only row).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from latris.operations.commit import auto_commit
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import Substrate
from latris.schema.bn import BNScenario, BNScenarioSet, BNTableOverride, CPTEntry
from latris.schema.common import ProvenanceOrigin

BASELINE = "baseline"
_TABLE = re.compile(r"^\s*(?P<node>[^\[\]=]+?)\s*(\[(?P<cond>[^\]]*)\])?\s*=\s*(?P<p>.+?)\s*$")
_BLOCKS = ("evidence", "soft", "likelihood", "interventions")


def path(paths: ProjectPaths) -> Path:
    return paths.view_attribute_path("bn", "scenarios")


def load(paths: ProjectPaths) -> BNScenarioSet:
    p = path(paths)
    return load_model(BNScenarioSet, p) if p.exists() else BNScenarioSet()


def list_scenarios(*, root: Path | None = None) -> list[BNScenario]:
    return load(require_project(root)).scenarios


def _find(name: str, scenarios: list[BNScenario]) -> BNScenario:
    for s in scenarios:
        if s.name.lower() == name.strip().lower():
            return s
    if name.strip().lower() == BASELINE:
        raise ValueError("'baseline' is the unchanged network, not a saved scenario")
    known = ", ".join(s.name for s in scenarios) or "(none yet)"
    raise ValueError(f"no BN scenario named {name!r}; saved scenarios: {known}")


def chain(name: str, scenarios: list[BNScenario]) -> list[BNScenario]:
    """The scenario and the ones it extends, root first. Refuses a cycle."""
    out: list[BNScenario] = []
    seen: set[str] = set()
    current: str | None = name
    while current is not None:
        s = _find(current, scenarios)
        if s.name.lower() in seen:
            trail = " → ".join([x.name for x in reversed(out)] + [s.name])
            raise ValueError(f"scenario {name!r} extends itself in a loop ({trail})")
        seen.add(s.name.lower())
        out.append(s)
        current = s.extends
    return list(reversed(out))


def merge(links: list[BNScenario]) -> BNScenario:
    """One scenario from a chain (root first): a later scenario's say about a factor replaces an earlier
    one's, whichever kind (observed, soft, likelihood, set); table overrides apply in order."""
    blocks: dict[str, dict] = {b: {} for b in _BLOCKS}
    tables: list[BNTableOverride] = []
    for s in links:
        for b in _BLOCKS:
            for node, value in getattr(s, b).items():
                for other in _BLOCKS:
                    blocks[other].pop(node, None)
                blocks[b][node] = value
        tables.extend(s.tables)
    last = links[-1]
    return last.model_copy(update={**blocks, "tables": tables})


def get(name: str, paths: ProjectPaths) -> BNScenario:
    """A saved scenario ready to apply: merged with the ones it extends (``extends`` kept)."""
    links = chain(name, load(paths).scenarios)
    return links[-1] if len(links) == 1 else merge(links)


# ── parsing the text forms ───────────────────────────────────────────


@dataclass(frozen=True)
class _Network:
    substrate: Substrate
    states: dict[str, list[str]]
    tables: dict[str, CPTEntry]

    def node(self, label: str) -> str:
        from latris.operations._resolve import resolve_target

        nid = resolve_target(label.strip(), self.substrate)
        if nid not in self.states:
            raise ValueError(f"{label.strip()!r} has no states yet, so it isn't in the network")
        return nid

    def state(self, nid: str, state: str, label: str) -> str:
        state = state.strip()
        if state not in self.states[nid]:
            raise ValueError(f"{state!r} is not a state of {label.strip()} (states: {', '.join(self.states[nid])})")
        return state


def _network(paths: ProjectPaths) -> _Network:
    from latris.operations import bn as bn_ops

    return _Network(
        substrate=load_model(Substrate, paths.conceptual_yaml),
        states={e.target_id: e.states for e in bn_ops.get_state_spaces(root=paths.root).entries},
        tables=bn_ops.effective_cpts(root=paths.root),
    )


def _pair(text: str, net: _Network) -> tuple[str, str]:
    if "=" not in text:
        raise ValueError(f"expected 'Factor=state', got {text!r}")
    label, state = text.rsplit("=", 1)
    nid = net.node(label)
    return nid, net.state(nid, state, label)


def _distribution(text: str, net: _Network, what: str) -> tuple[str, dict[str, float]]:
    from latris.operations.bn import parse_distribution

    label, dist = parse_distribution(text)
    nid = net.node(label)
    for st in dist:
        net.state(nid, st, label)
    if what == "soft" and sum(dist.values()) > 1 + 1e-6:
        raise ValueError(f"{text!r}: soft evidence is a probability for each state; they add up to more than 1")
    return nid, {st: float(v) for st, v in dist.items()}


def parse_table(text: str, net: _Network) -> BNTableOverride:
    m = _TABLE.match(text or "")
    if not m:
        raise ValueError(f"expected 'Factor[Parent=state,…]=p1,p2,…' or 'Factor=p1,p2,…', got {text!r}")
    label = m["node"]
    nid = net.node(label)
    table = net.tables.get(nid)
    if table is None:
        raise ValueError(f"{label.strip()} has no probability table yet; set one before overriding it")
    cond: dict[str, str] = {}
    for part in (m["cond"] or "").split(","):
        if not part.strip():
            continue
        pid, st = _pair(part, net)
        if pid not in table.parents:
            parents = ", ".join(_label(net, p) for p in table.parents) or "none"
            raise ValueError(f"{part.split('=')[0].strip()} is not a parent of {label.strip()} (parents: {parents})")
        cond[pid] = st
    try:
        probs = [float(x) for x in m["p"].split(",")]
    except ValueError as exc:
        raise ValueError(f"{m['p']!r} in {text!r} is not a list of numbers") from exc
    if len(probs) != len(table.states):
        raise ValueError(
            f"{label.strip()} has {len(table.states)} states ({', '.join(table.states)}); "
            f"give {len(table.states)} probabilities in that order, got {len(probs)}"
        )
    override = BNTableOverride(target_id=nid, parent_states=cond, p=probs)
    if not _rows(table, override):
        raise ValueError(f"{text!r} matches no row of {label.strip()}'s table")
    return override


def _label(net: _Network, nid: str) -> str:
    return next((e.label for e in net.substrate.entities if e.id == nid), nid)


# ── storage ──────────────────────────────────────────────────────────


def set_scenario(
    name: str,
    *,
    observe: list[str] | None = None,
    soft: list[str] | None = None,
    likelihood: list[str] | None = None,
    set_: list[str] | None = None,
    tables: list[str] | None = None,
    extends: str | None = None,
    description: str = "",
    reason: str = "",
    origin: ProvenanceOrigin = "human-direct",
    source_id: str | None = None,
    root: Path | None = None,
) -> tuple[BNScenario, str]:
    """Create or replace a named BN scenario from text forms (see the module docstring)."""
    paths = require_project(root)
    net = _network(paths)
    evidence = dict(_pair(t, net) for t in observe or [])
    interventions = dict(_pair(t, net) for t in set_ or [])
    soft_d = dict(_distribution(t, net, "soft") for t in soft or [])
    like_d = dict(_distribution(t, net, "likelihood") for t in likelihood or [])
    overrides = [parse_table(t, net) for t in tables or []]
    if not (evidence or interventions or soft_d or like_d or overrides):
        raise ValueError("a scenario needs at least one change: something observed, set, or a table override")
    store = load(paths)
    parent = _find(extends, store.scenarios).name if extends and extends.strip() else None
    scenario = BNScenario(
        name=name.strip(), description=description, extends=parent, evidence=evidence, soft=soft_d,
        likelihood=like_d, interventions=interventions, tables=overrides, reason=reason, origin=origin,
        source_id=source_id,
    )
    if parent is not None and parent.lower() == scenario.name.lower():
        raise ValueError(f"scenario {scenario.name!r} can't extend itself")
    store.scenarios = [s for s in store.scenarios if s.name.lower() != scenario.name.lower()] + [scenario]
    chain(scenario.name, store.scenarios)  # refuses a loop
    p = path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    dump_model(store, p)
    labels = {e.id: e.label for e in net.substrate.entities}
    sha = auto_commit(
        paths.root,
        subject=f"Set BN scenario {scenario.name}",
        body=("changes: " + "; ".join(describe_changes(scenario, labels)) + "\n"
              + (f"extends: {parent}\n" if parent else "")
              + f"origin: {origin}\nsource_id: {source_id}\nreason: {reason}"),
        paths=[p],
    )
    return scenario, sha


def remove_scenario(name: str, *, root: Path | None = None) -> str:
    paths = require_project(root)
    store = load(paths)
    scenario = _find(name, store.scenarios)
    children = [s.name for s in store.scenarios if (s.extends or "").lower() == scenario.name.lower()]
    if children:
        raise ValueError(
            f"{', '.join(children)} extend{'s' if len(children) == 1 else ''} {scenario.name!r}; "
            "remove or re-save those first"
        )
    store.scenarios = [s for s in store.scenarios if s.name != scenario.name]
    p = path(paths)
    dump_model(store, p)
    return auto_commit(paths.root, subject=f"Remove BN scenario {scenario.name}", paths=[p])


# ── applying a scenario ──────────────────────────────────────────────


def _rows(table: CPTEntry, o: BNTableOverride) -> list[int]:
    return [i for i, r in enumerate(table.rows)
            if all(r.parent_states.get(k) == v for k, v in o.parent_states.items())]


def apply_tables(
    tables: dict[str, CPTEntry], overrides: list[BNTableOverride], labels: dict[str, str] | None = None,
) -> tuple[dict[str, CPTEntry], dict[str, set[int]]]:
    """``tables`` with the overrides applied, and which rows of which table each override fixed."""
    labels = labels or {}
    out = dict(tables)
    fixed: dict[str, set[int]] = {}
    for o in overrides:
        table = out.get(o.target_id)
        name = labels.get(o.target_id, o.target_id)
        if table is None:
            raise ValueError(f"the scenario changes {name}'s table, which the network no longer has")
        if len(o.p) != len(table.states):
            raise ValueError(f"the scenario gives {len(o.p)} probabilities for {name}, which now has "
                             f"{len(table.states)} states ({', '.join(table.states)})")
        idx = _rows(table, o)
        if not idx:
            raise ValueError(f"the scenario's override of {name}'s table matches no row any more")
        rows = list(table.rows)
        for i in idx:
            rows[i] = rows[i].model_copy(update={"p": list(o.p)})
        out[o.target_id] = table.model_copy(update={"rows": rows})
        fixed.setdefault(o.target_id, set()).update(idx)
    return out, fixed


def describe_changes(s: BNScenario, labels: dict[str, str]) -> list[str]:
    """'observes Hot week = yes', 'sets Intake = closed', 'P(Bloom | Barrier = upgraded) = yes 10%, no 90%'."""
    lb = labels.get
    out = [f"observes {lb(k, k)} = {v}" for k, v in sorted(s.evidence.items())]
    out += [f"takes {lb(k, k)} as " + ", ".join(f"{st} {q:.0%}" for st, q in d.items())
            for k, d in sorted(s.soft.items())]
    out += [f"weighs an observation of {lb(k, k)} " + " : ".join(f"{st} {w:g}" for st, w in d.items())
            for k, d in sorted(s.likelihood.items())]
    out += [f"sets {lb(k, k)} = {v}" for k, v in sorted(s.interventions.items())]
    for o in s.tables:
        cond = ", ".join(f"{lb(k, k)} = {v}" for k, v in o.parent_states.items())
        out.append(f"P({lb(o.target_id, o.target_id)}{' | ' + cond if cond else ''}) → "
                   + ", ".join(f"{p:.3g}" for p in o.p))
    return out
