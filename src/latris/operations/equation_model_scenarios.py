"""The equation model's saved scenarios, in the shape shared code reads (``Formalism.scenario_store``).

Result staleness (``analysis_results``) and the analysis forms (``analysis_inputs``) ask a model type's
scenario store for ``load(paths).scenarios`` and ``chain(name, scenarios)``. Setting and removing
scenarios is in ``operations/equation_model.py``.
"""

from __future__ import annotations

from pathlib import Path

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model_or_default
from latris.schema.equation_model import EquationScenario, EquationScenarioSet


def path(paths: ProjectPaths) -> Path:
    return paths.view_attribute_path("equation_model", "scenarios")


def load(paths: ProjectPaths) -> EquationScenarioSet:
    return load_model_or_default(EquationScenarioSet, path(paths))


def chain(name: str, scenarios: list[EquationScenario]) -> list[EquationScenario]:
    """The scenario named ``name``, as a one-element chain: these scenarios don't extend one another."""
    found = [s for s in scenarios if s.name.casefold() == name.casefold()]
    if not found:
        known = ", ".join(s.name for s in scenarios) or "(none saved)"
        raise ValueError(f"no scenario named {name!r}. Saved: {known}")
    return found[:1]
