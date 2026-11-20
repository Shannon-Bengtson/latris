"""What a surface needs to run a declared analysis from a form: the choices its options take, and the run.

``capabilities.analysis_catalog`` says which analyses a model type has and what each option is (its
``x-input``). This module answers the project-specific half — which factors, states, scenarios, datasets
and columns there are to pick from — and runs one analysis from the options a person filled in, validated
against its build-spec model and recorded exactly as a build spec or share link records it.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from latris.operations.membership import members
from latris.repo.project import require_project
from latris.repo.yaml_io import load_model


def choices(model_type: str, *, root: Path | None = None) -> dict[str, Any]:
    """The values a form for ``model_type``'s analyses offers, by label/name as a build spec takes them:

    - ``factors``: the factors the type computes on (the whole map for the causal types), as
      ``{id, label}``;
    - ``states``: factor label → its states, for a type whose factors have them (a BN);
    - ``scenarios``: the type's saved scenarios, by name;
    - ``datasets``: registered datasets with their columns.
    """
    from latris.operations import formalisms
    from latris.operations.datasets import list_datasets
    from latris.schema import Substrate

    paths = require_project(root)
    substrate = load_model(Substrate, paths.conceptual_yaml)
    scope = members(paths, model_type)
    factors = [{"id": e.id, "label": e.label} for e in substrate.entities if scope is None or e.id in scope.entity_ids]
    label = {e.id: e.label for e in substrate.entities}

    plugin = formalisms.get(model_type)
    by_id = plugin.factor_states(paths) if plugin and plugin.factor_states else {}
    states = {label.get(i, i): s for i, s in by_id.items()}
    scenarios: list[str] = []
    if plugin and plugin.scenario_store:
        store = importlib.import_module(plugin.scenario_store)
        scenarios = [sc.name for sc in store.load(paths).scenarios]
    datasets = [{"name": d.name, "columns": [c.name for c in d.columns]} for d in list_datasets(root=paths.root)]
    return {"factors": factors, "states": states, "scenarios": scenarios, "datasets": datasets}


def run(options: dict[str, Any], *, root: Path | None = None) -> str:
    """Run and record the analysis ``options`` describes (``kind`` plus its options); returns the run id.

    Validated against the analysis's build-spec model: an option it doesn't take, or one of the wrong
    type, is refused (ValueError), as in a build spec.
    """
    from pydantic import TypeAdapter, ValidationError

    from latris.operations.analysis_replay import run_analysis
    from latris.schema.build_spec import SpecAnalysis

    try:
        analysis = TypeAdapter(SpecAnalysis).validate_python(options)
    except ValidationError as exc:
        where = lambda e: ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0])  # noqa: E731 — drop the kind
        problems = "; ".join(f"{where(e)}: {e['msg']}" for e in exc.errors())
        raise ValueError(f"These options can't run: {problems}") from exc
    return run_analysis(analysis, root=root)
