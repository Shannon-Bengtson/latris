"""Tests for the model type registry."""

from latris.schema.model_types import (
    MODEL_TYPE_REGISTRY,
    get_model_type,
    list_model_types,
)


def test_registry_populated_at_import():
    assert len(MODEL_TYPE_REGISTRY) >= 19


def test_stable_types():
    stable = list_model_types(include_planned=False)
    ids = {s.id for s in stable}
    assert ids == {"cld", "dag", "fcm", "bn", "sd"}


def test_all_types_include_planned():
    all_types = list_model_types(include_planned=True)
    ids = {s.id for s in all_types}
    expected = {
        "cld",
        "dag",
        "bn",
        "sd",
        "causal_dag",
        "gsn",
        "bow_tie",
        "fault_tree",
        "petri_net",
        "markov",
        "influence_diagram",
        "decision_tree",
        "event_tree",
        "fishbone",
        "theory_of_change",
        "argument_map",
        "fcm",
        "flowchart",
        "state_machine",
    }
    assert expected <= ids


def test_get_model_type_known():
    spec = get_model_type("cld")
    assert spec.display_name == "Causal Loop Diagram"
    assert spec.short_name == "CLD"
    assert spec.availability == "stable"
    assert spec.model_attributes == ("polarity",)


def test_get_model_type_unknown():
    import pytest

    with pytest.raises(ValueError, match="Unknown model type"):
        get_model_type("nonexistent")


def test_cld_spec():
    cld = get_model_type("cld")
    assert cld.model_attributes == ("polarity",)
    # CLDs require at least one feedback loop — that's the defining feature
    # of the formalism.
    assert cld.structural_validators == ("loops_present",)


def test_dag_spec():
    dag = get_model_type("dag")
    assert dag.model_attributes == ()
    assert dag.structural_validators == ("acyclicity",)


def test_sd_is_stable():
    sd = get_model_type("sd")
    assert sd.availability == "stable"
    assert "sd_no_algebraic_loops" in sd.structural_validators
    assert "sd_dimensional_consistency" in sd.structural_validators
    assert set(sd.allowed_roles) == {"stock", "flow", "auxiliary", "constant", "source_sink"}


def test_bn_is_stable():
    bn = get_model_type("bn")
    assert bn.availability == "stable"
    assert "acyclicity" in bn.structural_validators
    assert "state_space_defined" in bn.structural_validators
    assert "cpt_complete" in bn.structural_validators


def test_petri_net_has_bipartite_validator():
    pn = get_model_type("petri_net")
    assert "bipartite" in pn.structural_validators


def test_markov_is_planned():
    mc = get_model_type("markov")
    assert mc.availability == "planned"
    assert mc.structural_validators == ()


def test_influence_diagram_is_planned():
    iid = get_model_type("influence_diagram")
    assert iid.availability == "planned"
    assert "acyclicity" in iid.structural_validators
    assert "causal" in iid.required_edge_kinds


def test_fcm_is_stable():
    fcm = get_model_type("fcm")
    assert fcm.availability == "stable"
    assert "weight" in fcm.model_attributes


def test_spec_is_frozen():
    import pytest

    spec = get_model_type("cld")
    with pytest.raises(AttributeError):
        spec.id = "modified"  # type: ignore[misc]


def test_roadmap_built_iff_stable():
    for spec in MODEL_TYPE_REGISTRY.values():
        assert (spec.roadmap == "built") == (spec.availability == "stable"), spec.id


def test_register_rejects_inconsistent_roadmap():
    import pytest

    from latris.schema.model_types import ModelTypeSpec, register_model_type

    with pytest.raises(ValueError, match="roadmap"):
        register_model_type(ModelTypeSpec(
            id="__bogus", display_name="x", short_name="x", description="x", availability="planned", roadmap="built",
        ))
    assert "__bogus" not in MODEL_TYPE_REGISTRY


def test_planned_descriptions_carry_no_version_promises():
    import re

    for spec in MODEL_TYPE_REGISTRY.values():
        assert not re.search(r"\(v\d\+?\)", spec.description), spec.id
