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
