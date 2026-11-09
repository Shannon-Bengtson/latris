"""0.9.1 fixes: commas in scenario names, a capped loop summary, BN sensitivity ranges, extras."""

from __future__ import annotations

import pytest

from latris.operations import analysis_results as ar
from latris.operations import sd as sd_ops
from latris.operations import sd_scenarios
from latris.operations.sd_loops import describe

pytest.importorskip("scipy")


def test_scenario_names_can_contain_commas_and_old_keys_still_read(sd_bathtub_root):
    root = sd_bathtub_root
    sd_scenarios.set_scenario("Faster, cheaper", ["Drain Rate=0.2"], root=root)
    payload, runs = sd_ops.simulate_scenarios(["Faster, cheaper"], [], final_time=5, root=root)
    _, run_id = sd_ops.record_comparison(payload, runs, root=root)
    shown = ar.report_results(root=root)
    assert shown[0].run.id == run_id and ar._scope(shown[0].run) == {"Faster, cheaper"}

    old = shown[0].run.model_copy(update={"analysis_key": "sd-simulation|A,B"})
    assert ar._scope(old) == {"A", "B"}


def test_loop_summary_names_the_longest_periods_only():
    loops = [{"id": f"R{i}", "members": ["A", "B", "C", "D"]} for i in range(1, 7)]
    periods = [{"start": float(i), "end": float(i) + (0.1 if i % 2 else 2.0), "loops": [f"R{i % 6 + 1}"],
                "share": 0.6} for i in range(0, 12, 2)]
    payload = {"loops": loops, "sets": [{"dominant_periods": periods}], "time_units": "years"}
    text = describe(payload)
    assert text.count("dominates") == 4 and "(+2 shorter switches)" in text
    assert "A → B → C → …" in text


def test_bn_sensitivity_uses_the_table_uncertainty_when_set(tmp_path, git_identity):
    pytest.importorskip("pgmpy")
    from latris.operations import bn_sensitivity, uncertainty
    from tests.operations.test_bn_results import _flood

    root = _flood(tmp_path / "flood")
    wide = bn_sensitivity.sensitivity("Flood", "yes", root=root)
    assert {f.range_source for f in wide.findings} == {"any value from 0 to 1"}
    uncertainty.set_table_uncertainty("Flood", 50, root=root)
    narrow = bn_sensitivity.sensitivity("Flood", "yes", root=root)
    flood_rows = [f for f in narrow.findings if f.range_source.startswith("5th–95th")]
    assert flood_rows and all(0 < f.low < f.high < 1 for f in flood_rows)
    widest_before = max(f.influence for f in wide.findings if f.node_id == flood_rows[0].node_id)
    assert max(f.influence for f in flood_rows) < widest_before


def test_capabilities_report_extras_and_what_you_get_where():
    from latris.operations.capabilities import build_capability_manifest

    m = build_capability_manifest()
    assert set(m["extras"]["installed"]) == {"data", "quant"} and "latris[data,quant]" in m["extras"]["install"]
    assert "IS the shareable report" in m["what_you_get_where"]["link_is_the_report"]


def test_build_fails_loudly_when_an_extra_is_missing(tmp_path, git_identity, monkeypatch):
    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.operations import _bn_engine
    from latris.operations.init import init_project

    root = tmp_path / "p"
    init_project(root, statement="Will it be wet?")
    spec = root / "spec.yaml"
    spec.write_text(
        "model_type: bn\n"
        "factors: [{label: Rain}, {label: Wet}]\n"
        "links: [{from: Rain, to: Wet}]\n"
        "bn:\n"
        "  states: [{node: Rain, states: [yes, no]}, {node: Wet, states: [yes, no]}]\n"
        "  tables: [{node: Rain, probabilities: [0.2, 0.8]},\n"
        "           {node: Wet, parents: [Rain], probabilities: [0.9, 0.1, 0.1, 0.9]}]\n"
        "analyses: [{kind: bn_query, evidence: {Rain: 'yes'}}]\n",
        encoding="utf-8",
    )

    def missing():
        raise RuntimeError("Bayesian Network inference requires the 'quant' extra.")

    monkeypatch.setattr(_bn_engine, "_import_pgmpy", missing)
    monkeypatch.chdir(root)
    r = CliRunner().invoke(app, ["build", "--spec", str(spec)])
    assert r.exit_code == 1 and 'pip install "latris[data,quant]"' in r.stdout
    from latris.operations import nodes

    assert {n.label for n in nodes.list_nodes(root=root)} == {"Rain", "Wet"}  # the model is still built


def test_link_output_says_it_is_the_report(sd_bathtub_root, monkeypatch):
    from typer.testing import CliRunner

    from latris.cli.app import app

    monkeypatch.chdir(sd_bathtub_root)
    out = CliRunner().invoke(app, ["link"]).stdout
    assert "This link is the shareable report" in " ".join(out.split())
