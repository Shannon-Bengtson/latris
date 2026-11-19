"""Analyses in a build spec: one model per kind, each taking only its own options."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from latris.operations import formalisms
from latris.schema.build_spec import (
    ANALYSIS_MODELS,
    BuildSpec,
    analysis_kinds,
    analysis_model,
    make_analysis,
)


def test_every_registered_analysis_has_a_model():
    for r in formalisms.result_kinds():
        assert r.analysis in analysis_kinds()
    assert len(analysis_kinds()) == len(set(analysis_kinds()))


def test_a_kind_takes_its_own_options():
    a = make_analysis(kind="bn_compare", target="Health", state="poor", scenarios=["Trees"], runs=100)
    assert type(a) is analysis_model("bn_compare") and a.scenarios == ["Trees"]
    with pytest.raises(ValidationError):
        make_analysis(kind="mcda_analyse", evidence={"A": "yes"})  # an option MCDA doesn't take
    with pytest.raises(ValidationError):
        BuildSpec.model_validate({"analyses": [{"kind": "simulate", "treatment": "X"}]})
    with pytest.raises(ValidationError):
        BuildSpec.model_validate({"analyses": [{"kind": "no_such_analysis"}]})


def test_specs_written_before_typing_still_load():
    """Older specs and links carried every option of every kind; empty foreign ones are dropped."""
    old = {"kind": "mcda_analyse", "settings": {}, "scenarios": [], "evidence": {}, "target": None, "runs": None}
    spec = BuildSpec.model_validate({"analyses": [old, {"kind": "ft_analyse", "max_order": 2, "query": []}]})
    assert [a.kind for a in spec.analyses] == ["mcda_analyse", "ft_analyse"]
    assert spec.analyses[1].max_order == 2


def test_each_model_has_a_schema():
    for m in ANALYSIS_MODELS:
        schema = m.model_json_schema()
        assert schema["properties"]["kind"] and schema.get("description")
