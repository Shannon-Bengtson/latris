"""Every stable model type is fully wired — the guard that makes adding a formalism safe.

A formalism plugs in through one module in ``operations/formalisms/`` plus four central registries
(model-type spec, foundations, help, build-spec field). These tests fail, naming what's missing, when a
new type is half-wired.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import get_args

import pytest

from latris.operations import formalisms
from latris.operations.formalisms import CLAIM_SECTIONS, Formalism
from latris.schema.model_types import get_model_type, list_model_types

# Types that predate the plugin registry and keep their own wiring.
LEGACY = {"cld", "dag", "fcm", "sd"}
PLUGINS = formalisms.all_formalisms()
IDS = [f.model_type for f in PLUGINS]


def test_every_new_stable_type_is_a_plugin():
    stable = {s.id for s in list_model_types()}
    assert stable - LEGACY == set(IDS), "register a Formalism in operations/formalisms/ for each new stable type"
    for f in PLUGINS:
        assert get_model_type(f.model_type).availability == "stable"


def test_duplicate_registration_refused():
    with pytest.raises(ValueError, match="registered twice"):
        formalisms.register(Formalism(model_type=IDS[0], outcome_role=None, outcome_refusal="",
                                      outcome_ids=lambda paths: set()))


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_readiness_validators_match_the_spec(f):
    from latris.operations.readiness import _STRUCTURAL_VALIDATORS

    spec = get_model_type(f.model_type)
    assert f.structure_problems is not None
    assert set(f.validators) <= set(spec.structural_validators), "list the plugin's validators in its ModelTypeSpec"
    for name in spec.structural_validators:  # the plugin's own, or a shared one such as acyclicity
        assert name in _STRUCTURAL_VALIDATORS, f"no validator named {name!r}"
    gaps = [g for gs in f.validators.values() for g in gs]
    assert len(gaps) == len(set(gaps)), "a gap type is reported by two validators"


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_outcome(f):
    spec = get_model_type(f.model_type)
    assert f.outcome_refusal
    if f.outcome_role is not None:
        assert f.outcome_role in spec.allowed_roles and f.set_outcome is not None
    assert "outcome" not in spec.allowed_roles  # "outcome" is refused with outcome_refusal


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_results_are_registered_everywhere(f):
    from latris.operations.analysis_results import KIND_MODEL_TYPE, KIND_ORDER
    from latris.schema.build_spec import SpecAnalysis

    analysis_kinds = get_args(SpecAnalysis.model_fields["kind"].annotation)
    for r in f.results:
        assert r.kind in KIND_ORDER and KIND_MODEL_TYPE[r.kind] == f.model_type
        assert r.analysis in analysis_kinds, f"add {r.analysis!r} to SpecAnalysis.kind"
        assert r.title and callable(r.render) and callable(r.run) and callable(r.definition)


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_build_spec_block(f):
    from latris.cli.build_cmd import build
    from latris.schema.build_spec import BuildSpec

    assert f.spec_field in BuildSpec.model_fields, f"add a {f.spec_field!r} field to BuildSpec"
    assert f.spec_check and f.spec_apply and f.spec_export
    assert f"``{f.spec_field}``" in (build.__doc__ or ""), "list the block's keys in `latris build --help`"


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_foundations_and_help(f):
    from latris.operations.foundations import FOUNDATIONS
    from latris.server.help import HELP_TOPICS

    assert any(fd.applies_to == (f.model_type,) for fd in FOUNDATIONS), "add a foundations entry"
    command = f"latris {f.cli[1]} "
    assert any(command in t.body for t in HELP_TOPICS), f"add a help topic that shows `{command}…`"


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_cli_and_routes_load(f):
    import typer
    from fastapi import APIRouter

    module, name = f.cli
    assert isinstance(importlib.import_module(module).app, typer.Typer)
    assert isinstance(importlib.import_module(f.routes).router, APIRouter)
    assert len({p.cli[1] for p in PLUGINS}) == len(PLUGINS)


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_hooks_run_on_an_empty_project(f, tmp_path: Path, git_identity):
    """Claims, outcome, export, diagram and structure checks must cope with a project that doesn't use the type."""
    from latris.exporters.mermaid import render as mermaid
    from latris.operations.init import init_project
    from latris.operations.interpret import extract_claims
    from latris.repo.layout import ProjectPaths

    root = tmp_path / "empty"
    init_project(root, statement="Q?")
    paths = ProjectPaths(root)
    for section in CLAIM_SECTIONS:
        assert isinstance(formalisms.claims(f.model_type, paths, section), list)
    assert extract_claims("answer_to_question", f.model_type, root=root)
    assert f.outcome_ids(paths) == set()
    assert f.spec_export(paths, {}) is None
    assert f.structure_problems(root)  # an empty model is never complete
    assert mermaid(paths, model_type=f.model_type) == ""


@pytest.mark.parametrize(
    "a", formalisms.LEADING + formalisms.ANALYSES, ids=[a.result.kind for a in formalisms.LEADING + formalisms.ANALYSES]
)
def test_analysis_layers_are_registered_everywhere(a):
    from latris.operations.analysis_results import KIND_MODEL_TYPE, KIND_ORDER
    from latris.operations.foundations import _ANALYSIS_KIND_TO_ID, FOUNDATIONS
    from latris.schema.build_spec import SpecAnalysis

    assert get_model_type(a.model_type).availability == "stable"
    r = a.result
    assert r.kind in KIND_ORDER and KIND_MODEL_TYPE[r.kind] == a.model_type
    assert r.analysis in get_args(SpecAnalysis.model_fields["kind"].annotation)
    # sd-simulation is a core foundations entry of its own (see _ANALYSIS_KIND_TO_ID's note).
    found = _ANALYSIS_KIND_TO_ID.get(r.kind, r.kind if r.kind == "sd-simulation" else None)
    assert found in {fd.id for fd in FOUNDATIONS}, "map the kind to a foundations entry"
