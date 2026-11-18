"""Every stable model type is fully wired — the guard that makes adding a formalism safe.

A formalism plugs in through one module in ``operations/formalisms/`` plus four central registries
(model-type spec, foundations, help, build-spec field). These tests fail, naming what's missing, when a
new type is half-wired.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from latris.operations import formalisms
from latris.operations.formalisms import CLAIM_SECTIONS, Formalism
from latris.schema.model_types import get_model_type, list_model_types

# Every stable type is a plugin now (the causal types from formalisms/causal.py).
LEGACY: set[str] = set()
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
    if f.outcome_role == "outcome":  # the type keeps its outcome its own way (SD: its settings; causal: a role)
        assert f.set_outcome is not None
        return
    assert f.outcome_refusal
    if f.outcome_role is not None:
        assert f.outcome_role in spec.allowed_roles and f.set_outcome is not None
    assert "outcome" not in spec.allowed_roles  # "outcome" is refused with outcome_refusal


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_results_are_registered_everywhere(f):
    from latris.operations.analysis_results import KIND_MODEL_TYPE, KIND_ORDER
    from latris.schema.build_spec import analysis_kinds as spec_analysis_kinds

    analysis_kinds = spec_analysis_kinds()
    for r in f.results:
        assert r.kind in KIND_ORDER and KIND_MODEL_TYPE[r.kind] == f.model_type
        assert r.analysis in analysis_kinds, f"add a model for {r.analysis!r} to build_spec.SpecAnalysis"
        assert r.title and callable(r.render) and callable(r.run) and callable(r.definition)


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_build_spec_block(f):
    from latris.cli.build_cmd import build
    from latris.schema.build_spec import BuildSpec

    if f.spec_field is None:  # made of the substrate itself (the causal types): nothing more to write
        assert not (f.spec_check or f.spec_apply or f.spec_export or f.chat_ops)
        return
    assert f.spec_field in BuildSpec.model_fields, f"add a {f.spec_field!r} field to BuildSpec"
    assert f.spec_check and f.spec_apply and f.spec_export
    assert f"``{f.spec_field}``" in (build.__doc__ or ""), "list the block's keys in `latris build --help`"


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_foundations_and_help(f):
    from latris.operations.foundations import FOUNDATIONS
    from latris.server.help import HELP_TOPICS

    assert any(fd.applies_to == (f.model_type,) for fd in FOUNDATIONS), "add a foundations entry"
    if f.cli is None:  # commands shared with the substrate: its help topic is about the type
        name = get_model_type(f.model_type).display_name.lower()
        assert any(name.rstrip("s") in t.title.lower() for t in HELP_TOPICS), f"add a help topic for {name}"
        return
    command = f"latris {f.cli[1]} "
    assert any(command in t.body for t in HELP_TOPICS), f"add a help topic that shows `{command}…`"


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_cli_and_routes_load(f):
    import typer
    from fastapi import APIRouter

    if f.cli is None:
        assert f.routes is None  # the causal types use the substrate's commands and routes
        return
    module, name = f.cli
    assert isinstance(importlib.import_module(module).app, typer.Typer)
    assert isinstance(importlib.import_module(f.routes).router, APIRouter)
    with_cli = [p for p in PLUGINS if p.cli]
    assert len({p.cli[1] for p in with_cli}) == len(with_cli)


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
    assert f.spec_export is None or f.spec_export(paths, {}) is None
    assert f.structure_problems(root)  # an empty model is never complete
    assert mermaid(paths, model_type=f.model_type) == ""


@pytest.mark.parametrize("a", formalisms.ANALYSES, ids=[a.result.kind for a in formalisms.ANALYSES])
def test_analysis_layers_are_registered_everywhere(a):
    from latris.operations.analysis_results import KIND_MODEL_TYPE, KIND_ORDER
    from latris.operations.foundations import _ANALYSIS_KIND_TO_ID, FOUNDATIONS
    from latris.schema.build_spec import analysis_kinds

    assert get_model_type(a.model_type).availability == "stable"
    r = a.result
    assert r.kind in KIND_ORDER and KIND_MODEL_TYPE[r.kind] == a.model_type
    assert r.analysis in analysis_kinds()
    assert _ANALYSIS_KIND_TO_ID.get(r.kind) in {fd.id for fd in FOUNDATIONS}, "map the kind to a foundations entry"


def test_charts_need_declared_chart_kinds():
    from latris.operations.formalisms import Analysis, ResultKind

    r = ResultKind(kind="x-analysis", title="X", render=lambda p: [], analysis="x_analyse",
                   run=lambda a, root: "", definition=lambda p: None, charts=lambda p: [("x-bars", {})])
    with pytest.raises(ValueError, match="declare chart_kinds"):
        formalisms.register_analysis(Analysis(model_type="dag", result=r))
    assert all(bool(k.charts) == bool(k.chart_kinds) for k in formalisms.result_kinds())


def test_every_result_kind_declares_its_chat_tool():
    """Each analysis is a chat tool of its own (latris-app generates it from the manifest)."""
    import re

    kinds = formalisms.result_kinds()
    assert all(r.tool for r in kinds), [r.kind for r in kinds if not r.tool]
    names = [r.tool.name for r in kinds]
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"[a-z][a-z0-9_]{2,40}", n) for n in names)
    assert all(len(r.tool.description) > 40 for r in kinds)


@pytest.mark.parametrize("f", PLUGINS, ids=IDS)
def test_chat_ops_cover_the_block(f):
    """Chat writes every part of the block, each through exactly one declared operation."""
    import typing

    from latris.schema.build_spec import BuildSpec

    if f.spec_field is None:
        return
    annotation = BuildSpec.model_fields[f.spec_field].annotation
    block = next(a for a in typing.get_args(annotation) if a is not type(None))
    covered = [field for op in f.chat_ops for field in op.fields]
    assert sorted(covered) == sorted(block.model_fields), "declare a ChatOp for each block field, once"
    assert all(len(op.description) > 20 for op in f.chat_ops)


def test_chat_op_names_are_unique():
    names = [op.name for f in PLUGINS for op in f.chat_ops]
    assert len(names) == len(set(names))
