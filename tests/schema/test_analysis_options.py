"""Every analysis option is described and titled for the surfaces generated from it (chat tools, editor forms)."""

from latris.schema.build_spec import (
    ANALYSIS_MODELS,
    ANALYSIS_OPTION_DOCS,
    ANALYSIS_OPTION_INPUTS,
    ANALYSIS_OPTION_TITLES,
)

OPTIONS = {n for m in ANALYSIS_MODELS for n in m.model_fields if n != "kind"}
INPUT_KINDS = {
    "clock", "assignments", "scenarios", "scenario", "arm", "factors", "factor", "state", "factor-states",
    "factor-weights", "factor-values", "dataset", "column", "values", "column-map", "metric",
}


def test_every_option_is_described_and_titled():
    assert sorted(OPTIONS - set(ANALYSIS_OPTION_DOCS)) == []
    assert sorted(OPTIONS - set(ANALYSIS_OPTION_TITLES)) == []


def test_input_hints_name_options_that_exist_and_known_inputs():
    assert set(ANALYSIS_OPTION_INPUTS) <= OPTIONS
    assert set(ANALYSIS_OPTION_INPUTS.values()) <= INPUT_KINDS  # a surface must know each one


def test_schemas_carry_title_description_and_input():
    for m in ANALYSIS_MODELS:
        for name, prop in m.model_json_schema()["properties"].items():
            if name == "kind":
                continue
            assert prop["title"] == ANALYSIS_OPTION_TITLES[name] and prop["description"]
            assert prop.get("x-input") == ANALYSIS_OPTION_INPUTS.get(name)
