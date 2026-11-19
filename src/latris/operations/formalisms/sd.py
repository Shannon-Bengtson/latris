"""System dynamics as a formalism plugin — the last quantitative type to join the registry.

SD's results were already registry entries (``sd_results.py``, leading the report order); this
module registers the model type itself: its outcome (kept with the SD settings, since SD roles are
one per factor — so a stock can't also carry an ``outcome`` role), its structure problems (the
``sd check`` gaps), its build-spec block (check/apply/export for share links), its Mermaid sketch
(stocks as boxes, flows as hexagons, clouds as circles) and its CLI and routes. Readiness keeps its
named ``sd_*`` validators (``operations/readiness.py``), which the model-type spec lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from latris.operations.formalisms import Formalism, default_origin, register

# ── outcome of interest (kept with the SD settings) ─────────────────


def _outcome_ids(paths) -> set[str]:  # noqa: ANN001
    from latris.operations import sd as sd_ops

    outcome = sd_ops.get_settings(root=paths.root).outcome
    return {outcome} if outcome else set()


def _set_outcome(target: str, root: Path) -> tuple[str, str]:
    from latris.operations import sd as sd_ops

    return sd_ops.set_outcome(target, root=root)


# ── structure (the ``sd check`` gaps) ────────────────────────────────


@dataclass(frozen=True)
class _Problem:
    target_id: str | None
    gap_type: str
    message: str


def _problems(root: Path) -> list[_Problem]:
    from latris.operations import sd as sd_ops

    return [_Problem(g.element_id or None, g.gap_type, g.message) for g in sd_ops.check(root=root)]


# ── build spec and share links ───────────────────────────────────────


def _check(block, known, outcome: str | None) -> list[str]:  # noqa: ANN001
    names = (
        [("sd role", r.node) for r in block.roles]
        + [("sd stock", s.node) for s in block.stocks]
        + [("sd constant", c.node) for c in block.constants]
        + [("sd equation", e.node) for e in block.equations]
        + [("sd table", t.node) for t in block.tables]
        + [("sd uncertainty", u.node) for u in block.uncertainty]
        + [("sd scenario", line.split("=", 1)[0].strip()) for sc in block.scenarios for line in sc.set]
    )
    return [f"{where}: no factor named {n!r}" for where, n in names if not known(n)]


def _apply(block, verified_by: str, root: Path) -> int:  # noqa: ANN001
    return _apply_block(block, default_origin(verified_by), root)


def _apply_block(sd, default_origin: str, root: Path) -> int:
    """Roles first (equations need them), then values, equations, tables, uncertainty, scenarios."""
    from latris.operations import sd as sd_ops
    from latris.operations import sd_scenarios, uncertainty

    n = 0
    for r in sd.roles:
        sd_ops.set_role(r.node, r.role, root=root)
        n += 1
    if sd.settings:
        sd_ops.set_settings(**{("method" if k == "integration_method" else k): v
                               for k, v in sd.settings.items()}, root=root)
        n += 1
    for s in sd.stocks:
        sd_ops.set_initial_value(s.node, s.value, s.units, non_negative=s.non_negative,
                                 origin=s.origin or default_origin, source_id=s.source, root=root)
        n += 1
    for c in sd.constants:
        sd_ops.set_constant(c.node, c.value, c.units, origin=c.origin or default_origin, source_id=c.source,
                            root=root)
        n += 1
    for e in sd.equations:
        sd_ops.set_equation(e.node, e.expression, e.units, origin=e.origin or default_origin, source_id=e.source,
                            root=root)
        n += 1
    for t in sd.tables:
        sd_ops.set_table(t.node, [tuple(p) for p in t.points], t.x_units, t.y_units, extrapolate=t.extrapolate,
                         origin=t.origin or default_origin, source_id=t.source, root=root)
        n += 1
    for u in sd.uncertainty:
        uncertainty.set_uncertainty(u.node, u.distribution, u.params, reason=u.reason, source_id=u.source,
                                    origin=u.origin or default_origin, root=root)  # type: ignore[arg-type]
        n += 1
    from latris.operations.build import _parents_first

    for sc in _parents_first(sd.scenarios):
        sd_scenarios.set_scenario(sc.name, sc.set, description=sc.description, extends=sc.extends,
                                  reason=sc.reason, origin=sc.origin or default_origin,  # type: ignore[arg-type]
                                  source_id=sc.source, root=root)
        n += 1
    return n


def _export(paths, labels: dict[str, str]):  # noqa: ANN001, ANN202
    """System Dynamics parameters as spec entries (origins kept; reviews are not carried)."""
    from latris.operations import sd as sd_ops
    from latris.operations import sd_scenarios, uncertainty
    from latris.schema.build_spec import (
        SpecScenario,
        SpecSD,
        SpecSDEquation,
        SpecSDRole,
        SpecSDStock,
        SpecSDTable,
        SpecSDValue,
        SpecUncertainty,
    )

    def named(target_id: str) -> bool:
        return target_id in labels

    roles = [SpecSDRole(node=labels[r.target_id], role=r.value)
             for r in sd_ops.get_roles(root=paths.root).entries if named(r.target_id)]
    if not roles:
        return None
    stocks = [SpecSDStock(node=labels[e.target_id], value=e.initial_value, units=e.units,
                          non_negative=e.non_negative, origin=e.origin, source=e.source_id)
              for e in sd_ops.get_stocks(root=paths.root).entries if named(e.target_id)]
    constants = [SpecSDValue(node=labels[e.target_id], value=e.value, units=e.units, origin=e.origin,
                             source=e.source_id)
                 for e in sd_ops.get_constants(root=paths.root).entries if named(e.target_id)]
    equations = [SpecSDEquation(node=labels[e.target_id], expression=e.expression, units=e.units,
                                origin=e.origin, source=e.source_id)
                 for e in sd_ops.get_equations(root=paths.root).entries if named(e.target_id)]
    tables = [SpecSDTable(node=labels[e.target_id], points=[(p.x, p.y) for p in e.points], x_units=e.x_units,
                          y_units=e.y_units, extrapolate=e.extrapolate, origin=e.origin, source=e.source_id)
              for e in sd_ops.get_tables(root=paths.root).entries if named(e.target_id)]
    ranges = [SpecUncertainty(node=labels[e.target_id], distribution=e.distribution, params=e.params,
                              reason=e.reason, origin=e.origin, source=e.source_id)
              for e in uncertainty.sd_specs(paths).values() if named(e.target_id)]
    scenarios = [
        SpecScenario(
            name=s.name, extends=s.extends, description=s.description, reason=s.reason, origin=s.origin,
            source=s.source_id,
            set=[f"{labels[o.target_id]}={o.value!r} {o.units}" for o in s.overrides if named(o.target_id)],
        )
        for s in sd_scenarios.load(paths).scenarios
        if any(named(o.target_id) for o in s.overrides)
    ]
    stored = sd_ops.get_settings(root=paths.root).model_dump(exclude_none=True, exclude={"outcome"})
    return SpecSD(settings=stored, roles=roles, stocks=stocks, constants=constants, equations=equations, tables=tables,
                  uncertainty=ranges, scenarios=scenarios)


# ── membership ───────────────────────────────────────────────────────


def _computes_on(paths) -> set[str]:  # noqa: ANN001
    """The factors with an SD role, plus anything a flow edge touches."""
    from latris.operations import sd as sd_ops
    from latris.repo.yaml_io import load_model
    from latris.schema import Substrate

    nodes = {e.target_id for e in sd_ops._load_roles(paths).entries}
    for e in load_model(Substrate, paths.conceptual_yaml).edges:
        if e.kind == "flow":
            nodes |= {e.from_id, e.to_id}
    return nodes


# ── diagram ──────────────────────────────────────────────────────────

_SHAPES = {
    "stock": ('["', '"]'),  # a box
    "flow": ('{{"', '"}}'),  # a hexagon (a valve doesn't exist in Mermaid)
    "auxiliary": ('("', '")'),
    "constant": ('("', '")'),
    "source_sink": ('(("', '"))'),  # a cloud, as a circle
}


def _mermaid(paths, entities, edges) -> str:  # noqa: ANN001
    """Stocks as boxes, flows as hexagons, sources and sinks as circles; flows thick, links with polarity."""
    from latris.exporters.mermaid import _mermaid_text, _scoped
    from latris.operations import sd as sd_ops

    roles = {r.target_id: r.value for r in sd_ops.get_roles(root=paths.root).entries}
    if not roles:
        return ""
    _, _, polarity = _scoped(paths, "sd")
    alias = {e.id: f"n{i}" for i, e in enumerate(entities)}
    lines = ["flowchart LR"]
    for e in entities:
        left, right = _SHAPES.get(roles.get(e.id, ""), ('["', '"]'))
        lines.append(f"    {alias[e.id]}{left}{_mermaid_text(e.label)}{right}")
    for e in edges:
        if e.from_id not in alias or e.to_id not in alias:
            continue
        if e.kind == "flow":
            lines.append(f"    {alias[e.from_id]} ==> {alias[e.to_id]}")
        elif polarity.get(e.id):
            lines.append(f'    {alias[e.from_id]} -->|"{_mermaid_text(polarity[e.id])}"| {alias[e.to_id]}')
        else:
            lines.append(f"    {alias[e.from_id]} --> {alias[e.to_id]}")
    return "\n".join(lines) + "\n"


register(Formalism(
    model_type="sd",
    # The outcome is kept with the settings, not as a role: no outcome_role, but set_outcome.
    outcome_role=None,
    # Shown only if a caller refuses the role anyway; SD accepts "outcome" through set_outcome.
    outcome_refusal="Mark the factor a simulation explains with `latris view role sd <factor> outcome`.",
    outcome_ids=_outcome_ids,
    set_outcome=_set_outcome,
    structure_problems=_problems,
    spec_field="sd",
    spec_check=_check,
    spec_apply=_apply,
    spec_export=_export,
    mermaid=_mermaid,
    computes_on=_computes_on,
    source_label="Simulation",
    scope_noun="simulation",
    feedback_through_stocks=True,  # feedback runs through stocks (flow edges), never a causal-edge cycle
    finding_priority=("dynamics", "inference", "sensitivity", "structure"),
    handover_name="System Dynamics model",
    handover_command="latris sd check",
    scenario_store="latris.operations.sd_scenarios",
    cli=("latris.cli.sd_cmd", "sd"),
    routes="latris.server.routes.sd",
))
