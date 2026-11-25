"""Each analysis names the method it stands on, from the one foundations registry."""

from __future__ import annotations

from latris.operations.capabilities import analysis_catalog
from latris.operations.foundations import FOUNDATIONS, foundation_for_result


def test_every_analysis_names_its_method():
    ids = {f.id for f in FOUNDATIONS}
    for entry in analysis_catalog():
        m = entry["method"]
        assert m and m["id"] in ids and m["citation"], entry["kind"]
        assert set(m) == {"id", "method", "citation", "used_for", "limits"}


def test_an_analysis_with_its_own_entry_uses_it_and_others_use_their_type():
    assert foundation_for_result("bn-monte-carlo", "bn").id == "bn-psa"
    assert foundation_for_result("bn-query", "bn").id == "bn-exact-inference"
    assert foundation_for_result("sd-sensitivity", "sd").id == "sd-sensitivity"
    assert foundation_for_result("mcda-analysis", "mcda").id == "mcda-additive-value"
    assert foundation_for_result("nothing", "no-such-type") is None


def test_global_sensitivity_offers_each_type_only_the_options_it_reads():
    """One spec serves seven types; a form generated from the catalogue must not show a Bayesian network a
    simulation's metric, or a fault tree a factor to measure."""
    gsa = {e["model_type"]: set(e["analysis_schema"]["properties"]) for e in analysis_catalog() if e["analysis"].endswith("_gsa")}
    assert {"variable", "metric"} <= gsa["sd"] and not {"state", "evidence", "output"} & gsa["sd"]
    assert {"variable", "state", "evidence"} <= gsa["bn"] and not {"metric", "output"} & gsa["bn"]
    assert "output" in gsa["fault_tree"] and not {"variable", "metric", "state", "evidence"} & gsa["fault_tree"]
    assert all({"method", "n", "seed"} <= options for options in gsa.values())
