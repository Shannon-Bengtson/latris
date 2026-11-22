"""Equation model: formulas with units, the valid range, scenarios, sweep, Monte Carlo, and the project surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import equation_model as eq
from latris.operations import nodes as node_ops
from latris.operations._sd_eval import ALGEBRAIC_FUNCTIONS, FUNCTIONS, EquationError, parse
from latris.operations._units import display, with_units
from latris.operations.init import init_project
from latris.operations.readiness import assess_readiness

# Manning's equation for uniform flow in a rectangular channel.
LABELS = ("Depth", "Width", "Slope", "Roughness", "Hydraulic radius", "Velocity", "Discharge")
R = 9.6 / 10.4  # area / wetted perimeter at depth 1.2, width 8
V = R ** (2 / 3) * 0.001 ** 0.5 / 0.035
Q = V * 9.6


def test_the_evaluator_takes_a_function_list_per_type():
    assert parse("LOG10(x) + TAN(y)", functions=ALGEBRAIC_FUNCTIONS, clock=False).names == {"x", "y"}
    with pytest.raises(EquationError, match="no clock"):
        parse("x * TIME", functions=ALGEBRAIC_FUNCTIONS, clock=False)
    for name in ("STEP", "RAMP", "PULSE", "TABLE", "SMOOTH", "DELAY3"):
        assert name in FUNCTIONS and name not in ALGEBRAIC_FUNCTIONS
        with pytest.raises(EquationError, match="unknown function"):
            parse(f"{name}(x, 1)", functions=ALGEBRAIC_FUNCTIONS, clock=False)
    with pytest.raises(EquationError, match="unknown function"):  # SD's own list is unchanged
        parse("LOG10(x)")
    assert parse("x * TIME").names == {"x"}


def test_units_as_a_reader_sees_them():
    assert display("m**3/s") == "m³/s" and display("m**2") == "m²" and display("kg/m**3/s**2") == "kg/m³/s²"
    assert display("s/m**(1/3)") == "s/m^(1/3)" and display("m**2.5") == "m^2.5" and display("m**23") == "m^23"
    assert display("dimensionless") == "" and with_units("3", "dimensionless") == "3"
    assert with_units("8.2", "m**3/s") == "8.2 m³/s"


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "channel"
    init_project(root, statement="How much water can this channel carry?")
    for label in LABELS:
        node_ops.add_node(label, root=root)
    monkeypatch.chdir(root)
    return root


def _build(root: Path) -> None:
    eq.set_value("Depth", 1.2, "m", role="input", valid_min=0.2, valid_max=3, root=root)
    eq.set_value("Width", 8, "m", role="input", root=root)
    eq.set_value("Slope", 0.001, "dimensionless", role="input", root=root)
    eq.set_value("Roughness", 0.035, "s/m**(1/3)", role="parameter", valid_min=0.025, valid_max=0.05,
                 source_id="chow1959", verification="human-verified", root=root)
    eq.set_formula("Hydraulic radius", "width * depth / (width + 2 * depth)", "m", role="computed", root=root)
    eq.set_formula("Velocity", "hydraulic_radius ** (2/3) * SQRT(slope) / roughness", "m/s", role="computed",
                   source_id="manning1891", root=root)
    eq.set_formula("Discharge", "velocity * width * depth", "m**3/s", role="output", root=root)


def test_readiness_and_the_kernel(project):
    assert {"eq_no_output"} <= {g.gap_type for g in assess_readiness("equation_model", root=project).gaps}
    _build(project)
    assert assess_readiness("equation_model", root=project).can_switch
    m = eq.load(root=project)
    by = {m.labels[i]: v for i, v in eq.compute(m).items()}
    assert by["Hydraulic radius"] == pytest.approx(R) and by["Velocity"] == pytest.approx(V)
    assert by["Discharge"] == pytest.approx(Q)
    depth = next(i for i, label in m.labels.items() if label == "Depth")
    deeper = eq.compute(m, {depth: 2.0})  # pure: the model's own value is untouched
    assert deeper[depth] == 2.0 and m.values[depth].value == 1.2
    assert [o["quantity"] for o in eq.outside_range(m, eq.compute(m, {depth: 5.0}))] == ["Depth"]


def test_build_does_not_ask_for_links_the_formulas_will_add(project):
    from latris.operations.project import update_selected_models
    from latris.operations.readiness import assess_transition_readiness

    def gate() -> str:
        return next(t.light for t in assess_transition_readiness(root=project).transitions
                    if t.to_phase == "formalise")

    assert gate() == "red"  # unlinked factors, no model type chosen
    update_selected_models(["equation_model"], root=project)
    assert gate() == "green"
    update_selected_models(["equation_model", "cld"], root=project)  # a loop map still needs its links
    assert gate() == "red"


def test_a_formula_adds_the_links_it_reads(project):
    from latris.operations.edges import list_edges

    _build(project)
    labels = {n.id: n.label for n in node_ops.list_nodes(root=project)}
    links = {(labels[e.from_id], labels[e.to_id]) for e in list_edges(root=project)}
    assert links == {("Width", "Hydraulic radius"), ("Depth", "Hydraulic radius"), ("Hydraulic radius", "Velocity"),
                     ("Slope", "Velocity"), ("Roughness", "Velocity"), ("Velocity", "Discharge"),
                     ("Width", "Discharge"), ("Depth", "Discharge")}
    eq.set_formula("Discharge", "velocity * width * depth", "m**3/s", root=project)  # again: nothing to add
    assert len(list_edges(root=project)) == 8
    assert eq.formula_reads("velocity * widht", root=project) == {"velocity": "Velocity", "widht": "widht"}


def test_setter_rules(project):
    _build(project)
    with pytest.raises(ValueError, match="not in the equation model"):
        eq.set_formula("Velocity", "hydraulic_radius * gravity", "m/s", root=project)
    with pytest.raises(ValueError, match="refers to itself"):
        eq.set_formula("Velocity", "velocity * 2", "m/s", root=project)
    with pytest.raises(ValueError, match="no clock"):
        eq.set_formula("Velocity", "depth / TIME", "m/s", root=project)
    with pytest.raises(ValueError, match="unknown function"):
        eq.set_formula("Velocity", "STEP(depth, 1)", "m/s", root=project)
    with pytest.raises(ValueError, match="unknown or malformed units"):
        eq.set_value("Depth", 1, "blorps", root=project)
    with pytest.raises(ValueError, match="a formula belongs to a computed quantity or an output"):
        eq.set_formula("Depth", "width", "m", root=project)
    with pytest.raises(ValueError, match="a value belongs to an input or a parameter"):
        eq.set_value("Velocity", 1, "m/s", root=project)
    with pytest.raises(ValueError, match="finite"):
        eq.set_value("Depth", float("nan"), "m", root=project)
    with pytest.raises(ValueError, match="not an equation-model role"):
        eq.set_role("Depth", "stock", root=project)
    from latris.operations.view_roles import set_role

    with pytest.raises(ValueError, match="results are its outputs"):  # an "outcome" here is an output
        set_role("Velocity", "equation_model", "outcome", root=project)


def test_structure_problems(project):
    from latris.operations.edges import add_edge, remove_edge

    _build(project)

    def gaps() -> set[str]:
        return {p.gap_type for p in eq.structure_problems(root=project)}

    eq.set_formula("Velocity", "hydraulic_radius * SQRT(slope) / roughness", "m/s", root=project)  # wrong dimensions
    problems = eq.structure_problems(root=project)
    assert [p.gap_type for p in problems] == ["eq_units"] and "declared units are m/s" in problems[0].message
    eq.set_role("Discharge", "computed", root=project)  # units are checked before the model has an output
    assert gaps() == {"eq_no_output", "eq_units"}
    eq.set_role("Discharge", "output", root=project)
    eq.set_formula("Velocity", "hydraulic_radius ** (2/3) * SQRT(slope) / roughness", "m/s", root=project)
    assert gaps() == set()

    add_edge("Slope", "Discharge", root=project)  # the map claims a dependency the formula doesn't have
    add_edge("Velocity", "Depth", root=project)  # …and a link into something that is given
    assert gaps() == {"eq_unused_link"} and len(eq.structure_problems(root=project)) == 2
    remove_edge("Slope -> Discharge", root=project)
    remove_edge("Velocity -> Depth", root=project)
    remove_edge("Velocity -> Discharge", root=project)
    assert gaps() == {"eq_missing_link"}
    eq.set_formula("Discharge", "velocity * width * depth", "m**3/s", root=project)  # puts the link back
    assert gaps() == set()

    eq.set_role("Width", "computed", root=project)  # a formula quantity with no formula
    assert "eq_no_formula" in gaps()
    eq.set_formula("Width", "discharge / (velocity * depth)", "m", root=project)
    assert "eq_circular" in gaps()
    eq.set_value("Width", 8, "m", role="input", root=project)
    node_ops.add_node("Hydraulic-radius", root=project)  # the same formula name as Hydraulic radius
    eq.set_value("Hydraulic-radius", 1, "m", role="input", root=project)
    assert "eq_name_collision" in gaps()
    eq.remove("Hydraulic-radius", root=project)
    eq.remove("Roughness", root=project)
    assert "eq_unknown_reference" in gaps()
    with pytest.raises(ValueError, match="not in the equation model"):
        eq.remove("Roughness", root=project)
    with pytest.raises(ValueError, match="incomplete"):
        eq.sweep(root=project)
    assert eq.evaluate(root=project)["problems"] and "incomplete" in eq.describe(eq.evaluate(root=project))


def test_scenarios_and_evaluate(project):
    _build(project)
    eq.set_scenario("Flood", ["Depth=350 cm"], description="bankfull", root=project)  # compatible units convert
    eq.set_scenario("Steep", ["Slope=0.004"], root=project)
    with pytest.raises(ValueError, match="can't replace it"):
        eq.set_scenario("Bad", ["Depth=3 s"], root=project)
    with pytest.raises(ValueError, match="a scenario value belongs to an input or a parameter"):
        eq.set_scenario("Bad", ["Velocity=3"], root=project)
    with pytest.raises(ValueError, match="expected 'Quantity=value"):
        eq.set_scenario("Bad", ["Depth is 3"], root=project)
    with pytest.raises(ValueError, match="one value"):
        eq.set_scenario("Bad", ["Depth=3", "Depth=4"], root=project)
    with pytest.raises(ValueError, match="at least one value"):
        eq.set_scenario("Bad", [], root=project)

    p = eq.evaluate(set=["Width=10 m"], root=project)
    arms = {a["name"]: a for a in p["arms"]}
    assert list(arms) == ["Reference", "Flood", "Steep", "What-if"] and p["scenarios"] == ["Flood", "Steep"]
    assert arms["Reference"]["values"]["Discharge"] == pytest.approx(Q)
    assert arms["Flood"]["changes"] == [{"quantity": "Depth", "value": 3.5, "units": "m", "from": 1.2}]
    assert [o["quantity"] for o in arms["Flood"]["outside"]] == ["Depth"] and not arms["Steep"]["outside"]
    assert arms["Steep"]["values"]["Discharge"] == pytest.approx(2 * Q)  # velocity goes with the root of the slope
    assert "outside their valid range (Depth)" in eq.describe(p) and "m³/s" in eq.describe(p)
    assert p["unsourced"] and "Roughness" not in p["unverified"]
    roles = [q["role"] for q in p["quantities"]]
    assert roles == ["input", "input", "input", "parameter", "computed", "computed", "output"]
    sha, run_id = eq.record(p, root=project)
    assert sha and run_id

    only = eq.evaluate(scenarios=["steep"], root=project)  # by name, any case
    assert [a["name"] for a in only["arms"]] == ["Reference", "Steep"]
    with pytest.raises(ValueError, match="no scenario named"):
        eq.evaluate(scenarios=["Drought"], root=project)
    eq.remove_scenario("Steep", root=project)
    assert [s.name for s in eq.get_scenarios(root=project).scenarios] == ["Flood"]


def test_a_recorded_result_goes_stale_only_with_what_it_used(project):
    from latris.operations.analysis_results import list_results

    _build(project)
    eq.set_scenario("Flood", ["Depth=2.5 m"], root=project)
    eq.record(eq.evaluate(scenarios=[], root=project), root=project)  # the reference values only

    def stale() -> bool:
        return list_results(root=project)[0][2]

    eq.set_scenario("Flood", ["Depth=2.8 m"], root=project)  # a scenario the run didn't use
    assert not stale()
    eq.set_value("Width", 9, "m", root=project)
    assert stale()


def test_sweep(project):
    _build(project)
    p = eq.sweep(input="Depth", root=project)  # the valid range by default
    assert (p["low"], p["high"], p["steps"]) == (0.2, 3, 25) and not p["extrapolated"]
    assert p["target"] == "Discharge" and p["shape"] == "increasing" and len(p["x"]) == 25
    assert p["reference"] == {"x": 1.2, "y": pytest.approx(Q)}
    assert 1.4 < p["elasticity"] < 1.6  # a little under 5/3: the banks add to the wetted perimeter
    assert "1% rise in Depth" in eq.describe_sweep(p)
    wide = eq.sweep(input="Depth", low=0.1, high=6, steps=5, root=project)
    assert wide["extrapolated"] and "outside Depth's valid range" in eq.describe_sweep(wide)
    falling = eq.sweep(input="rough", target="Velocity", root=project)  # a parameter, by the start of its label
    assert falling["shape"] == "decreasing" and falling["elasticity"] == pytest.approx(-1, abs=1e-3)
    assert falling["target"] == "Velocity" and set(falling["series"]) == {"Discharge", "Velocity"}
    half = eq.sweep(input="Width", root=project)  # no valid range: half to one and a half times the value
    assert (half["low"], half["high"]) == (4, 12)
    broken = eq.sweep(input="Slope", low=-0.001, high=0.001, steps=3, root=project)  # SQRT of a negative
    assert broken["failed"] == [-0.001] and broken["series"]["Discharge"][0] is None
    assert "can't be evaluated at 1 of the 3 points" in eq.describe_sweep(broken)
    for bad, message in (({"input": "Velocity"}, "no single input or parameter"), ({"steps": 1}, "steps"),
                         ({"low": 3, "high": 1}, "low below high"), ({"target": "Depth"}, "no single output")):
        with pytest.raises(ValueError, match=message):
            eq.sweep(**{"input": "Depth", **bad}, root=project)
    eq.set_value("Slope", 0, "dimensionless", root=project)
    with pytest.raises(ValueError, match="give the range to sweep"):
        eq.sweep(input="Slope", root=project)
    assert eq.record_sweep(p, root=project)[1]


def test_uncertainty_and_monte_carlo(project):
    _build(project)
    with pytest.raises(ValueError, match="no input or parameter has an uncertainty range"):
        eq.monte_carlo(root=project)
    with pytest.raises(ValueError, match="lies outside this distribution"):
        eq.set_uncertainty("Roughness", "uniform", {"min": 0.04, "max": 0.05}, root=project)
    with pytest.raises(ValueError, match="an uncertainty range belongs to"):
        eq.set_uncertainty("Velocity", "uniform", {"min": 0, "max": 1}, root=project)
    eq.set_uncertainty("Roughness", "triangular", {"min": 0.02, "mode": 0.035, "max": 0.06}, reason="by eye",
                       root=project)
    p = eq.monte_carlo(runs=300, seed=3, root=project)
    out = p["outputs"][0]
    assert p["primary"] == "Discharge" and out["units"] == "m**3/s" and out["point"] == pytest.approx(Q)
    assert out["p5"] < out["p50"] < out["p95"] and p["evaluated"] == 300
    driver = p["drivers"][0]
    assert driver["input"] == "Roughness" and driver["spearman"] == pytest.approx(-1)  # the only uncertain value
    assert 0 < driver["outside_valid"] < 1  # the range reaches beyond 0.025–0.05
    assert p["fixed"] == ["Depth", "Slope", "Width"]
    assert "most of the spread comes from Roughness" in eq.describe_monte_carlo(p)
    assert eq.monte_carlo(runs=300, seed=3, root=project)["outputs"] == p["outputs"]  # seeded
    with pytest.raises(ValueError, match="runs must be"):
        eq.monte_carlo(runs=5, root=project)
    assert eq.record_monte_carlo(p, root=project)[1]
    eq.clear_uncertainty("Roughness", root=project)
    with pytest.raises(ValueError, match="no uncertainty range to clear"):
        eq.clear_uncertainty("Roughness", root=project)


def test_draws_the_formulas_cannot_take_are_left_out(project):
    _build(project)
    eq.set_uncertainty("Slope", "uniform", {"min": -0.0002, "max": 0.002}, root=project)
    p = eq.monte_carlo(runs=200, root=project)
    assert 150 < p["evaluated"] < 200
    eq.set_uncertainty("Slope", "uniform", {"min": -0.02, "max": 0.002}, root=project)
    with pytest.raises(ValueError, match="could be evaluated for only"):
        eq.monte_carlo(runs=200, root=project)


def test_removing_a_quantity_takes_its_rows_and_range(project):
    _build(project)
    eq.set_uncertainty("Roughness", "uniform", {"min": 0.03, "max": 0.04}, root=project)
    _, removed, _ = eq.remove("Roughness", root=project)
    assert removed == 3  # role, value, range
    assert not eq.specs(eq.require_project(project)) and "Roughness" in {n.label for n in node_ops.list_nodes(
        root=project)}


SPEC = """
model_type: equation_model
outcome: Discharge
factors: [{label: Depth}, {label: Width}, {label: Velocity}, {label: Flow area}, {label: Discharge}]
sources:
  - {key: gauging2024, title: Gauging survey, year: 2024}
equation_model:
  values:
    - {node: Depth, role: input, value: 1.2, units: m, valid_min: 0.2, valid_max: 3}
    - {node: Width, role: input, value: 8, units: m}
    - {node: Velocity, role: parameter, value: 0.9, units: m/s, source: gauging2024, verified: true}
  formulas:
    # Discharge is listed before the quantity its formula reads.
    - {node: Discharge, role: output, expression: velocity * flow_area, units: m**3/s}
    - {node: Flow area, role: computed, expression: width * depth, units: m**2}
  uncertainty:
    - {node: Velocity, distribution: normal, params: {mean: 0.9, sd: 0.1}, reason: gauging scatter}
  scenarios:
    - {name: Flood, set: ["Depth=2.5 m"], description: bankfull}
analyses:
  - kind: eq_evaluate
  - {kind: eq_sweep, input: Depth, steps: 5}
  - {kind: eq_monte_carlo, runs: 100, seed: 2}
"""


@pytest.fixture
def built(tmp_path: Path, git_identity, monkeypatch):
    from latris.operations.build import build_from_spec, load_spec

    root = tmp_path / "built"
    init_project(root, statement="How much water?")
    monkeypatch.chdir(root)
    return root, build_from_spec(load_spec(SPEC), root=root)


def test_build_spec_and_share_link(built, tmp_path, git_identity):
    from latris.operations.build import build_from_spec
    from latris.operations.share_link import export_spec

    root, result = built
    assert len(result.analyses) == 3 and not result.notes
    assert "Discharge reads: flow_area = Flow area, velocity = Velocity" in result.info
    p = eq.evaluate(root=root)
    assert p["arms"][0]["values"]["Discharge"] == pytest.approx(0.9 * 9.6)
    _, spec = export_spec(model_type="equation_model", root=root)
    block = spec.equation_model
    assert block and len(block.values) == 3 and len(block.formulas) == 2 and len(block.uncertainty) == 1
    assert block.scenarios[0].set == ["Depth=2.5 m"]
    assert [a.kind for a in spec.analyses] == ["eq_evaluate", "eq_sweep", "eq_monte_carlo"]
    sweep = next(a for a in spec.analyses if a.kind == "eq_sweep")
    assert (sweep.input, sweep.target, sweep.low, sweep.high, sweep.steps) == ("Depth", "Discharge", 0.2, 3, 5)
    copy = tmp_path / "copy"
    init_project(copy, statement="copy")
    build_from_spec(spec, root=copy)
    assert eq.evaluate(root=copy)["arms"] == p["arms"]
    assert eq.monte_carlo(runs=100, seed=2, root=copy) == eq.monte_carlo(runs=100, seed=2, root=root)


def test_spec_check_names_unknown_factors(tmp_path, git_identity):
    from latris.operations.build import load_spec, preview_build

    root = tmp_path / "p"
    init_project(root, statement="Q?")
    preview = preview_build(load_spec(SPEC.replace("node: Width, role: input", "node: Breadth, role: input")),
                            root=root)
    assert not preview.ok and any("no factor named 'Breadth'" in e for e in preview.problems)


def test_report_diagram_claims(built):
    from latris.exporters.markdown import render
    from latris.exporters.mermaid import render as mermaid
    from latris.operations.interpret import extract_claims
    from latris.repo.layout import ProjectPaths

    root, _ = built
    md = render(ProjectPaths(root), model_type="equation_model", ai=False, chart_markers=True)
    assert "### Equation model: results" in md and "`velocity * flow_area`" in md and "8.64 m³/s" in md
    assert "### Equation model: response to an input: Discharge against Depth" in md
    assert "the sweep stays inside it" in md
    assert "### Equation model: uncertainty (Monte Carlo)" in md and "gauging scatter" in md
    assert "Equation models: sourced formulas with dimensional analysis" in md
    for chart in ("eq-scenarios", "eq-response", "mc-strip"):
        assert f'"chart": "{chart}"' in md
    src = mermaid(ProjectPaths(root), model_type="equation_model")
    assert '(["Depth<br/>1.2 m"])' in src and '[["Discharge<br/>m³/s"]]' in src and src.count("-->") == 4
    answer = extract_claims("answer_to_question", "equation_model", root=root)
    assert any("Discharge = 8.64 m³/s at the reference values" in c for c in answer)
    structure = extract_claims("structural_summary", "equation_model", root=root)
    assert any("2 input(s) and 1 parameter(s) feed 2 formula(s)" in c for c in structure)
    gaps = extract_claims("evidence_gaps", "equation_model", root=root)
    assert any("Evidence coverage: 1/5 equation model quantities" in c and "1/5 verified" in c for c in gaps), gaps
    assert any("No valid range stated for: Velocity, Width" in c for c in gaps)
    sens = extract_claims("sensitivity", "equation_model", root=root)
    assert any("1 of 3 input(s) and parameter(s) carry an uncertainty range" in c for c in sens)
    assert any("As Depth goes from" in c for c in sens) and not any("betweenness" in c for c in sens)
    limits = extract_claims("assumptions_limitations", "equation_model", root=root)
    assert any("treats 2 value(s) as exact" in c for c in limits)


def test_routes(built):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    root, _ = built
    c = TestClient(create_app(project_root=root))
    assert c.get("/api/eq/check").json()["ready"] is True
    model = c.get("/api/eq/model").json()
    by = {q["quantity"]: q for q in model["quantities"]}
    assert by["Discharge"]["value"] == pytest.approx(8.64) and by["Discharge"]["reads"] == ["Flow area", "Velocity"]
    assert by["Velocity"]["uncertainty"]["distribution"] == "normal" and model["scenarios"][0]["name"] == "Flood"
    assert by["Discharge"]["units"] == "m**3/s" and by["Discharge"]["units_display"] == "m³/s"
    assert not model["problems"]

    r = c.post("/api/eq/value", json={"node": "Width", "value": 10, "units": "m", "valid_max": 12})
    assert r.status_code == 200 and r.json()["result"]["valid_max"] == 12 and r.json()["commit_sha"]
    assert c.post("/api/eq/value", json={"node": "Discharge", "value": 1, "units": "m"}).status_code == 422
    r = c.post("/api/eq/formula", json={"node": "Discharge", "expression": "velocity * flow_area * 1", "units": "m**3/s"})
    assert r.status_code == 200 and r.json()["result"]["reads"] == {"flow_area": "Flow area", "velocity": "Velocity"}
    assert c.post("/api/eq/formula", json={"node": "Discharge", "expression": "nope", "units": "m"}).status_code == 422
    assert c.post("/api/eq/role", json={"node": "Flow area", "role": "output"}).json()["result"]["role"] == "output"
    assert c.post("/api/eq/role", json={"node": "Flow area", "role": "stock"}).status_code == 422

    r = c.post("/api/eq/scenario", json={"name": "Low", "set": ["Depth=0.4 m"]})
    assert r.status_code == 200 and r.json()["result"]["overrides"][0]["value"] == 0.4
    assert c.delete("/api/eq/scenario/Low").json()["result"] == {"removed": "Low"}
    assert c.delete("/api/eq/scenario/Low").status_code == 422
    r = c.post("/api/eq/uncertainty", json={"node": "Depth", "distribution": "uniform",
                                            "params": {"min": 1.0, "max": 1.5}})
    assert r.status_code == 200 and r.json()["result"]["parameter_cell_id"] == "equation_model:value"
    assert c.post("/api/eq/uncertainty/clear", json={"node": "Depth"}).status_code == 200

    r = c.post("/api/eq/evaluate", json={"record": False}).json()
    assert r["commit_sha"] is None and r["result"]["arms"][1]["name"] == "Flood"
    assert c.post("/api/eq/evaluate").json()["commit_sha"]
    r = c.post("/api/eq/sweep", json={"input": "Depth", "steps": 4, "record": False}).json()
    assert len(r["result"]["x"]) == 4 and r["commit_sha"] is None
    r = c.post("/api/eq/monte-carlo", json={"runs": 50}).json()
    assert r["result"]["evaluated"] == 50 and r["result"]["run_id"]
    assert c.post("/api/eq/monte-carlo", json={"runs": 1}).status_code == 422

    assert c.post("/api/eq/remove", json={"node": "Flow area"}).json()["result"]["rows_removed"] == 2
    assert c.get("/api/eq/check").json()["ready"] is False

    # The generic analysis surface (the app's forms) lists and runs this type's analyses too.
    kinds = {a["analysis"] for a in c.get("/api/analyses", params={"model_type": "equation_model"}).json()["analyses"]}
    assert kinds == {"eq_evaluate", "eq_sweep", "eq_monte_carlo"}
    assert c.get("/api/analyses/choices", params={"model_type": "equation_model"}).json()["scenarios"] == ["Flood"]


def test_cli(project):
    import json

    from typer.testing import CliRunner

    from latris.cli.app import app

    runner = CliRunner()

    def run(*args: str, code: int = 0) -> str:
        out = runner.invoke(app, ["eq", *args])
        assert out.exit_code == code, out.output
        return out.output

    run("check", code=1)
    run("input", "Depth", "1.2", "m", "--min", "0.2", "--max", "3")
    run("input", "Width", "8", "m")
    run("input", "Slope", "0.001", "dimensionless")
    run("parameter", "Roughness", "0.035", "s/m**(1/3)", "--source", "chow1959", "--verified")
    run("formula", "Hydraulic radius", "width * depth / (width + 2 * depth)", "m")
    run("formula", "Velocity", "hydraulic_radius ** (2/3) * SQRT(slope) / roughness", "m/s", "--source", "manning1891")
    assert "(in m³/s)" in run("formula", "Discharge", "velocity * width * depth", "m**3/s")
    assert "No output" in run("check", code=1)
    run("role", "Discharge", "output")
    assert "complete" in run("check")
    shown = run("show")
    assert "Roughness" in shown and "s/m^(1/3)" in shown and "chow1959" in shown
    assert "No scenarios saved" in run("scenarios")
    run("scenario", "Design flood", "--set", "Depth=3.5 m", "-d", "bankfull")
    assert "Design flood" in run("scenarios") and "3.5 m" in run("scenarios")
    out = run("evaluate")
    assert "Design flood" in out and "outside its valid range" in out and "recorded" in out
    assert "recorded" not in run("evaluate", "--scenario", "Design flood", "--set", "Width=9", "--no-record")
    out = run("sweep", "--input", "Depth", "--steps", "5")
    assert "increasing" in out and "recorded" in out
    run("uncertainty", "Roughness", "triangular", "--min", "0.025", "--mode", "0.035", "--max", "0.05",
        "--reason", "range for natural streams")
    out = run("monte-carlo", "--runs", "200")
    assert "What drives Discharge" in out and "Held fixed" in out and "recorded" in out
    run("uncertainty", "Roughness", "--clear")
    run("scenario", "Design flood", "--remove")
    assert "removed" in run("remove", "Slope")
    run("check", code=1)

    data = json.loads(runner.invoke(app, ["--json", "eq", "show"]).stdout)["result"]
    assert {q["role"] for q in data["quantities"]} == {"input", "parameter", "computed", "output"}
    assert data["problems"][0]["gap_type"] == "eq_unknown_reference"
