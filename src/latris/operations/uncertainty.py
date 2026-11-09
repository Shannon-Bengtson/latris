"""Parameter uncertainty — distributions over quantitative values, with provenance.

Stored once per project at ``substrate/attributes/parameter-uncertainty.yaml``
(a cross-cutting attribute, so other model types can annotate their
parameters later). For System Dynamics a constant or a stock's initial value
can carry one: ``parameter_cell_id`` is ``sd:constant`` or ``sd:initial_value``.

Values are in the parameter's declared units. The distribution is a modelling
claim like any other: ``origin``, ``source_id`` and ``reason`` record who chose
it and on what basis, and reports flag ranges that are AI-proposed or unsourced.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations._sampling import Sampler
from latris.operations.commit import auto_commit
from latris.repo.layout import ProjectPaths
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.attributes import ParameterUncertainty, ParameterUncertaintySet
from latris.schema.common import ProvenanceOrigin

SD_CELLS = {"constant": "sd:constant", "stock": "sd:initial_value"}


def load(paths: ProjectPaths) -> ParameterUncertaintySet:
    p = paths.parameter_uncertainty_yaml
    return load_model(ParameterUncertaintySet, p) if p.exists() else ParameterUncertaintySet()


def sd_specs(paths: ProjectPaths) -> dict[str, ParameterUncertainty]:
    """SD uncertainty specs by target id (constants and stock initial values)."""
    return {
        e.target_id: e
        for e in load(paths).entries
        if e.parameter_cell_id in SD_CELLS.values() and e.distribution != "unknown"
    }


def list_uncertainty(*, root: Path | None = None) -> list[ParameterUncertainty]:
    return load(require_project(root)).entries


def set_uncertainty(
    target: str,
    distribution: str,
    params: dict[str, float],
    *,
    reason: str = "",
    source_id: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    root: Path | None = None,
) -> tuple[ParameterUncertainty, str]:
    """Give an SD constant or stock initial value a distribution (replacing any previous one)."""
    from latris.operations import sd as sd_ops

    paths = require_project(root)
    _, target_id, label = sd_ops._resolve(paths, target)
    role = sd_ops._require_role(paths, target_id, label, ("constant", "stock"), "an uncertainty range")
    cell = SD_CELLS[role]
    store = sd_ops.get_constants(root=paths.root) if role == "constant" else sd_ops.get_stocks(root=paths.root)
    current = next((e for e in store.entries if e.target_id == target_id), None)
    if current is None:
        raise ValueError(f"{label} has no value yet; set it before describing its uncertainty")

    entry = ParameterUncertainty(
        target_id=target_id,
        distribution=distribution,
        params=params,  # type: ignore[arg-type]
        parameter_cell_id=cell,
        reason=reason,
        source_id=source_id,
        origin=origin,
    )
    sampler = Sampler(entry)  # proves the distribution can be sampled (e.g. truncation leaves mass)
    lo, hi = sampler.quantile(0.001), sampler.quantile(0.999)
    value = current.value if role == "constant" else current.initial_value  # type: ignore[union-attr]
    if not lo <= value <= hi:
        raise ValueError(
            f"{label}'s current value {value:g} {current.units} lies outside this distribution "
            f"(99.8% of it is between {lo:.4g} and {hi:.4g}); values are in {current.units}"
        )

    s = load(paths)
    s.entries = [e for e in s.entries if not (e.target_id == target_id and e.parameter_cell_id == cell)] + [entry]
    path = paths.parameter_uncertainty_yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(s, path)
    pretty = ", ".join(f"{k}={v:g}" for k, v in params.items())
    sha = auto_commit(
        paths.root,
        subject=f"Set uncertainty on {label}: {distribution}({pretty})",
        body=f"target: {target_id}\ncell: {cell}\nunits: {current.units}\norigin: {origin}\n"
        f"source_id: {source_id}\nreason: {reason}",
        paths=[path],
    )
    return entry, sha


def clear_uncertainty(target: str, *, root: Path | None = None) -> str:
    from latris.operations import sd as sd_ops

    paths = require_project(root)
    _, target_id, label = sd_ops._resolve(paths, target)
    s = load(paths)
    kept = [e for e in s.entries if e.target_id != target_id]
    if len(kept) == len(s.entries):
        raise ValueError(f"{label} has no uncertainty range to clear")
    s.entries = kept
    dump_model(s, paths.parameter_uncertainty_yaml)
    return auto_commit(paths.root, subject=f"Clear uncertainty on {label}", paths=[paths.parameter_uncertainty_yaml])


# ── Bayesian network tables ──────────────────────────────────────────

BN_TABLE = "bn:cpt"


def row_cell(parents: list[str], parent_states: dict[str, str]) -> str:
    """The cell id of one table row: ``bn:cpt:<parent_id>=<state>,...`` in the table's parent order."""
    return BN_TABLE + ":" + ",".join(f"{p}={parent_states[p]}" for p in parents)


def bn_specs(paths: ProjectPaths) -> dict[str, dict[str, ParameterUncertainty]]:
    """BN table uncertainty by node: ``{node_id: {cell_id: spec}}`` (``bn:cpt`` for the whole table)."""
    out: dict[str, dict[str, ParameterUncertainty]] = {}
    for e in load(paths).entries:
        if e.distribution == "dirichlet" and (e.parameter_cell_id or "").startswith(BN_TABLE):
            out.setdefault(e.target_id, {})[e.parameter_cell_id or BN_TABLE] = e
    return out


def set_table_uncertainty(
    node: str,
    n: float,
    *,
    row: str | None = None,
    reason: str = "",
    source_id: str | None = None,
    origin: ProvenanceOrigin = "human-direct",
    root: Path | None = None,
) -> tuple[ParameterUncertainty, str]:
    """Say a probability table (or one row of it) is "worth about ``n`` observations".

    Monte Carlo then samples each row from a Dirichlet centred on its current
    probabilities: small ``n`` is a rough guess, large ``n`` a well-founded table.
    ``row`` ("Rain=yes,Sprinkler=no", by label) narrows it to one parent combination.
    """
    from latris.operations import bn as bn_ops
    from latris.operations._resolve import resolve_target
    from latris.repo.yaml_io import load_model as _load
    from latris.schema import Substrate

    paths = require_project(root)
    substrate = _load(Substrate, paths.conceptual_yaml)
    node_id = resolve_target(node, substrate)
    label = next((e.label for e in substrate.entities if e.id == node_id), node)
    tables = {e.target_id: e for e in bn_ops.get_cpts(root=paths.root).entries}
    noisy = {e.target_id for e in bn_ops.get_noisy_or(root=paths.root).entries}
    if node_id not in tables and node_id not in noisy:
        raise ValueError(f"{label} has no probability table yet; set one before describing its uncertainty")
    if n <= 0:
        raise ValueError("n (how many observations the table is worth) must be positive")

    cell = BN_TABLE
    if row:
        if node_id in noisy:
            raise ValueError(f"{label} is a Noisy-OR; its uncertainty applies to the whole table, not one row")
        table = tables[node_id]
        spaces = {e.target_id: e.states for e in bn_ops.get_state_spaces(root=paths.root).entries}
        given: dict[str, str] = {}
        for part in row.split(","):
            if "=" not in part:
                raise ValueError(f"a row is 'Parent=state,...', got {row!r}")
            name, state = (x.strip() for x in part.rsplit("=", 1))
            pid = resolve_target(name, substrate)
            if pid not in table.parents:
                raise ValueError(f"{name} is not a parent of {label}")
            if state not in spaces.get(pid, []):
                raise ValueError(f"{state!r} is not a state of {name} (states: {spaces.get(pid, [])})")
            given[pid] = state
        missing = [p for p in table.parents if p not in given]
        if missing:
            names = {e.id: e.label for e in substrate.entities}
            raise ValueError(f"the row must give every parent; missing {', '.join(names.get(m, m) for m in missing)}")
        cell = row_cell(table.parents, given)

    entry = ParameterUncertainty(
        target_id=node_id, distribution="dirichlet", params={"n": float(n)}, parameter_cell_id=cell,
        reason=reason, source_id=source_id, origin=origin,
    )
    s = load(paths)
    s.entries = [e for e in s.entries if not (e.target_id == node_id and e.parameter_cell_id == cell)] + [entry]
    path = paths.parameter_uncertainty_yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(s, path)
    where = f" (row {row})" if row else ""
    sha = auto_commit(
        paths.root,
        subject=f"Set uncertainty on {label}'s probabilities{where}: worth {n:g} observations",
        body=f"target: {node_id}\ncell: {cell}\norigin: {origin}\nsource_id: {source_id}\nreason: {reason}",
        paths=[path],
    )
    return entry, sha
