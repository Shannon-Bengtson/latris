"""Contract and predict: declaring a model's inputs and outputs, running it statelessly, pinning a version."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import latris
from latris.operations import contract, predict
from latris.operations import equation_model as eq
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.repo.layout import pinned_cache_dir

# 8 m wide, 1.5 m deep, 0.9 m/s.
Q = 0.9 * 8 * 1.5


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "channel"
    init_project(root, statement="How much water can this channel carry?")
    for label in ("Depth", "Width", "Velocity", "Flow area", "Discharge"):
        node_ops.add_node(label, root=root)
    eq.set_value("Depth", 1.5, "m", role="input", valid_min=0.2, valid_max=3, root=root)
    eq.set_value("Width", 8, "m", role="input", root=root)
    eq.set_value("Velocity", 0.9, "m/s", role="parameter", root=root)
    eq.set_formula("Flow area", "width * depth", "m**2", role="computed", root=root)
    eq.set_formula("Discharge", "velocity * flow_area", "m**3/s", role="output", root=root)
    monkeypatch.chdir(root)
    return root


def _commits(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout)


# ── the contract ─────────────────────────────────────────────────────


def test_a_contract_is_drafted_from_the_model_then_edited(project):
    with pytest.raises(ValueError, match="no contract yet"):
        predict.predict(root=project)
    c, _ = contract.init("equation_model", root=project)
    # Inputs go in; parameters (coefficients of the method) are not exposed unless asked; outputs come out.
    assert [(i.name, i.units) for i in c.inputs] == [("depth", "m"), ("width", "m")]
    assert [(o.name, o.kind, o.units) for o in c.outputs] == [("discharge", "value", "m**3/s")]
    assert contract.check(root=project) == []
    with pytest.raises(ValueError, match="already has a contract"):
        contract.init("equation_model", root=project)

    d = contract.describe(root=project)
    depth = d["inputs"][0]
    assert (depth["label"], depth["default"], depth["valid_min"], depth["valid_max"]) == ("Depth", 1.5, 0.2, 3)
    first = d["hash"]

    entry, _ = contract.set_input("equation_model", "Velocity", name="speed", units="km/hour", valid_max=10, root=project)
    assert entry.name == "speed" and contract.describe(root=project)["hash"] != first
    speed = next(i for i in contract.describe(root=project)["inputs"] if i["name"] == "speed")
    assert speed["default"] == pytest.approx(3.24)  # the model's 0.9 m/s, in the contract's units
    contract.set_input("equation_model", "Depth", default=2.0, root=project)  # the same input, changed
    # ...and it keeps its place: a table of inputs doesn't reshuffle under the person editing a row.
    assert [i.name for i in contract.get("equation_model", root=project).inputs] == ["depth", "width", "speed"]
    # A range the wrong way round is refused in plain words (no pydantic report), and nothing changes.
    with pytest.raises(ValueError, match="^input 'depth': the valid range needs its minimum below its maximum$"):
        contract.set_input("equation_model", "Depth", valid_min=5, valid_max=3, root=project)
    assert contract.get("equation_model", root=project).inputs[0].default == 2.0
    contract.set_output("equation_model", "Flow area", root=project)
    assert {o.name for o in contract.get("equation_model", root=project).outputs} == {"discharge", "flow_area"}

    for call, message in (
        (lambda: contract.set_input("equation_model", "Discharge", root=project), "can't be an input"),
        (lambda: contract.set_output("equation_model", "Depth", root=project), "can't be an output"),
        (lambda: contract.set_input("equation_model", "Width", units="s", root=project), "can't set it"),
        (lambda: contract.set_input("equation_model", "Width", name="speed", root=project), "name"),
        (lambda: contract.set_output("equation_model", "Discharge", metric="peak", root=project), "has no metric"),
        (lambda: contract.set_output("equation_model", "Discharge", kind="series", root=project), "not a series"),
        (lambda: contract.remove("equation_model", "nope", root=project), "no input or output named"),
        (lambda: contract.init("cld", root=project), "has no contract"),
    ):
        with pytest.raises(ValueError, match=message):
            call()
    contract.remove("equation_model", "flow_area", root=project)
    cands = contract.candidates("equation_model", root=project)
    assert [(c["label"], c["in_contract"]) for c in cands["inputs"]] == [
        ("Depth", ["depth"]), ("Width", ["width"]), ("Velocity", ["speed"])]
    assert [c["label"] for c in cands["outputs"]] == ["Discharge", "Flow area"]


def test_check_says_when_the_contract_no_longer_fits(project):
    contract.init("equation_model", root=project)
    eq.set_role("Discharge", "computed", root=project)  # the model has no output any more
    assert any("isn't ready to run" in p for p in contract.check(root=project))
    eq.set_role("Discharge", "output", root=project)
    eq.remove("Width", root=project)
    problems = contract.check(root=project)
    assert any("input 'width'" in p and "no longer" in p for p in problems)
    with pytest.raises(ValueError, match="can't be run"):
        predict.predict(root=project)


# ── predict ──────────────────────────────────────────────────────────


def test_predict_is_stateless_and_says_what_it_ran(project):
    contract.init("equation_model", root=project)
    before = _commits(project)
    r = predict.predict(root=project)
    assert r["outputs"]["discharge"] == {"value": pytest.approx(Q), "units": "m**3/s", "label": "Discharge"}
    assert r["inputs"]["depth"] == {"value": 1.5, "units": "m", "source": "model"} and r["warnings"] == []
    p = r["provenance"]
    assert p["commit"] == git.head_sha(project) and not p["uncommitted_changes"] and p["ref"] is None
    assert p["contract_hash"] == contract.describe(root=project)["hash"] and p["latris_version"] == latris.__version__

    r = predict.predict({"depth": "250 cm", "width": {"value": 10, "units": "m"}}, root=project)  # units convert
    assert r["outputs"]["discharge"]["value"] == pytest.approx(0.9 * 10 * 2.5)
    assert r["inputs"]["depth"] == {"value": 2.5, "units": "m", "source": "given"}

    r = predict.predict({"depth": 4}, root=project)  # outside the valid range: used as given, and said
    assert r["outputs"]["discharge"]["value"] == pytest.approx(0.9 * 8 * 4)
    assert r["warnings"] == ["input depth = 4 m is outside its valid range (0.2 to 3 m): the result is an "
                             "extrapolation"]

    contract.set_input("equation_model", "Width", default=6, root=project)
    assert predict.predict(root=project)["inputs"]["width"] == {"value": 6.0, "units": "m", "source": "default"}
    contract.set_input("equation_model", "Width", default=None, required=True, root=project)
    with pytest.raises(ValueError, match="'width' is required"):
        predict.predict(root=project)
    for inputs, message in (({"breadth": 1}, "unknown input"), ({"width": "wide"}, "needs a number"),
                            ({"width": "3 s"}, "can't be used")):
        with pytest.raises(ValueError, match=message):
            predict.predict({"width": 8, **inputs}, root=project)
    assert predict.parse_assignment("depth = 250 cm") == ("depth", "250 cm")
    with pytest.raises(ValueError, match="expected 'input=value'"):
        predict.parse_assignment("depth")

    assert _commits(project) == before + 2  # the two contract edits; no call wrote anything
    assert git.is_dirty(project) is False


def test_a_fixed_value_outside_its_range_is_reported_too(project):
    contract.init("equation_model", root=project)
    eq.set_value("Velocity", 0.9, "m/s", valid_max=0.5, root=project)  # not a contract input
    assert predict.predict(root=project)["warnings"] == [
        "Velocity = 0.9 m/s is outside its valid range in the model (–0.5): the result is an extrapolation"]


def test_unsaved_changes_are_flagged(project):
    contract.init("equation_model", root=project)
    (project / "notes.txt").write_text("scratch")
    r = predict.predict(root=project)
    assert r["provenance"]["uncommitted_changes"] and "aren't saved yet" in r["warnings"][-1]


# ── pinning a version ────────────────────────────────────────────────


def test_a_pinned_version_runs_as_it_was(project):
    from latris.operations import lineage

    contract.init("equation_model", root=project)
    v1 = git.head_sha(project)
    milestone, _ = lineage.create_milestone("Signed off", maturity="approved", root=project)
    eq.set_value("Velocity", 1.2, "m/s", root=project)

    now = predict.predict(root=project)
    then = predict.predict(ref=v1, root=project)
    assert now["outputs"]["discharge"]["value"] == pytest.approx(1.2 * 12)
    assert then["outputs"]["discharge"]["value"] == pytest.approx(Q)
    assert then["provenance"]["commit"] == v1 and then["provenance"]["ref"] == v1
    assert (pinned_cache_dir() / v1 / ".graph-tooling").is_dir() and not (pinned_cache_dir() / v1 / ".git").exists()

    named = predict.predict(ref="Signed off", require="approved", root=project)  # a milestone, by its name
    assert named["provenance"]["commit"] == milestone.commit_sha
    assert named["outputs"]["discharge"]["value"] == pytest.approx(Q)
    assert named["provenance"]["review"]["milestone"] == {"name": "Signed off", "maturity": "approved"}
    assert predict.predict(ref=v1[:10], root=project)["provenance"]["commit"] == v1  # a prefix; reuses the export
    with pytest.raises(ValueError, match="is proposed, not approved"):
        predict.predict(require="approved", root=project)
    with pytest.raises(ValueError, match="require must be"):
        predict.predict(require="blessed", root=project)
    with pytest.raises(ValueError, match="no commit, milestone or version"):
        predict.predict(ref="v9", root=project)
    assert git.is_dirty(project) is False  # pinning touched nothing in the project


def test_the_python_api_loads_once_and_calls_many_times(project):
    contract.init("equation_model", root=project)
    v1 = git.head_sha(project)
    eq.set_value("Velocity", 1.2, "m/s", root=project)

    model = latris.load(project, ref=v1)
    assert model.commit == v1 and model.model_type == "equation_model" and v1[:10] in repr(model)
    assert [i["name"] for i in model.contract["inputs"]] == ["depth", "width"]
    assert model.contract["provenance"]["commit"] == v1
    rows = model.predict_many([{"depth": d} for d in (1.0, 2.0, 3.0)])
    assert [r["outputs"]["discharge"]["value"] for r in rows] == pytest.approx([7.2, 14.4, 21.6])
    assert latris.load(project).predict()["outputs"]["discharge"]["value"] == pytest.approx(1.2 * 12)
    with pytest.raises(AttributeError):
        latris.nothing  # noqa: B018


def test_compare_sorts_changes_by_what_they_mean_for_a_caller(project):
    contract.init("equation_model", root=project)
    v1 = git.head_sha(project)
    assert contract.compare(v1, root=project)["verdict"] == "same"

    eq.set_value("Velocity", 1.0, "m/s", root=project)
    d = contract.compare(v1, root=project)
    assert d["verdict"] == "internal" and d["model_changed"] and d["base_hash"] == d["head_hash"]

    contract.set_input("equation_model", "Velocity", root=project)
    contract.set_input("equation_model", "Depth", default=2.0, valid_max=4, root=project)
    contract.set_output("equation_model", "Flow area", root=project)
    v2 = git.head_sha(project)
    d = contract.compare(v1, v2, root=project)
    assert d["verdict"] == "compatible" and d["breaking"] == []
    assert d["compatible"] == ["input depth: default changed from None to 2.0", "input depth: valid range changed",
                               "input velocity was added", "output flow_area was added"]

    contract.remove("equation_model", "width", root=project)
    contract.set_input("equation_model", "Depth", units="cm", default=None, required=True, root=project)
    contract.remove("equation_model", "flow_area", root=project)
    node_ops.add_node("Gate", root=project)
    eq.set_value("Gate", 1, "dimensionless", role="input", root=project)
    contract.set_input("equation_model", "Gate", required=True, root=project)
    d = contract.compare(v2, root=project)
    assert d["verdict"] == "breaking"
    assert d["breaking"] == ["input depth changed from a value in m to a value in cm", "input depth is now required",
                             "input width was removed", "input gate was added and is required",
                             "output flow_area was removed"]
    assert contract.compare(v1, v1, root=project)["verdict"] == "same"


# ── system dynamics and Bayesian networks ────────────────────────────


@pytest.fixture(scope="module")
def system_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from latris.testing import build_example

    with pytest.MonkeyPatch.context() as mp:
        for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            mp.setenv(k, "Test Runner")
        for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
            mp.setenv(k, "test-runner@example.invalid")
        return build_example("system", tmp_path_factory.mktemp("system") / "p")


@pytest.fixture
def system(system_template: Path, tmp_path: Path, git_identity) -> Path:
    return Path(shutil.copytree(system_template, tmp_path / "system"))


def test_system_dynamics_takes_values_and_returns_runs_or_measures(system):
    c, _ = contract.init("sd", root=system)
    assert {i.name for i in c.inputs} >= {"emission_rate", "dispersal_rate"}  # the constants
    assert all(o.kind == "series" for o in c.outputs)
    out = c.outputs[0].name
    contract.set_output("sd", "PM2.5 Load", name="peak_load", metric="peak", root=system)
    contract.set_output("sd", "PM2.5 Load", name="final_load", kind="value", root=system)  # final by default
    contract.set_input("sd", "PM2.5 Load", name="starting_load", root=system)  # a stock's starting value

    model = latris.load(system, model_type="sd")
    base = model.predict()
    series = base["outputs"][out]["series"]
    assert series["time_units"] == "year" and len(series["times"]) == len(series["values"]) > 10
    assert series["values"][0] == pytest.approx(20) and base["outputs"][out]["units"] == "tonne"
    assert base["outputs"]["peak_load"]["value"] == pytest.approx(max(series["values"]))
    assert base["outputs"]["final_load"]["value"] == pytest.approx(series["values"][-1])

    more = model.predict({"emission_rate": 240, "starting_load": "0.05 kilotonne"})
    assert more["outputs"][out]["series"]["values"][0] == pytest.approx(50)
    assert more["outputs"]["final_load"]["value"] > base["outputs"]["final_load"]["value"]
    assert model.predict()["outputs"]["final_load"] == base["outputs"]["final_load"]  # one call doesn't leak into the next
    with pytest.raises(ValueError, match="say which model type"):
        contract.init("bn", root=system)
        predict.predict(root=system)


def test_a_bayesian_network_takes_states_and_returns_distributions(system):
    pytest.importorskip("pgmpy")
    c, _ = contract.init("bn", root=system)
    assert all(i.kind == "state" and i.mode == "observe" for i in c.inputs) and c.inputs
    assert all(o.kind == "distribution" for o in c.outputs)
    contract.set_output("bn", "Respiratory Health", name="health", root=system)
    contract.set_output("bn", "Vehicle Emissions", name="emissions", root=system)
    contract.set_input("bn", "Transport Policy", name="policy", root=system)
    contract.set_input("bn", "Air Quality Index", name="air", mode="set", root=system)
    d = contract.describe("bn", root=system)
    assert next(i for i in d["inputs"] if i["name"] == "policy")["states"] == ["lax", "strict"]

    model = latris.load(system, model_type="bn")
    prior = model.predict()["outputs"]["emissions"]
    assert prior["units"] is None and prior["distribution"]["low"] == pytest.approx(0.55)
    assert model.predict({"policy": "strict"})["outputs"]["emissions"]["distribution"]["low"] == pytest.approx(0.8)
    assert model.predict({"policy": "lax"})["outputs"]["emissions"]["distribution"]["low"] == pytest.approx(0.3)
    # Setting the air quality fixes what health responds to: worse air, worse health, whatever the policy.
    poor = model.predict({"air": "poor", "policy": "lax"})["outputs"]["health"]["distribution"]
    good = model.predict({"air": "good", "policy": "lax"})["outputs"]["health"]["distribution"]
    assert good["good"] > poor["good"]
    assert poor == pytest.approx(model.predict({"air": "poor", "policy": "strict"})["outputs"]["health"]["distribution"])
    with pytest.raises(ValueError, match="not a state of Transport Policy"):
        model.predict({"policy": "medium"})
    with pytest.raises(ValueError, match="not a state"):
        contract.set_input("bn", "Transport Policy", default="medium", root=system)
    # An output that is also observed is certain.
    contract.set_output("bn", "Transport Policy", name="policy_seen", root=system)
    seen = latris.load(system, model_type="bn").predict({"policy": "strict"})["outputs"]["policy_seen"]
    assert seen["distribution"] == {"lax": 0.0, "strict": 1.0}


def test_only_types_with_a_forward_calculation_have_a_predictor():
    from latris.operations import formalisms

    assert {f.model_type for f in formalisms.all_formalisms() if f.predictor} == {
        "equation_model", "sd", "bn", "fcm", "fault_tree", "bow_tie", "event_tree", "decision_tree", "markov", "mcda"}


# ── routes and CLI ───────────────────────────────────────────────────


def test_routes(project):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    c = TestClient(create_app(project_root=project))
    assert c.get("/api/contract/types").json() == {
        "available": ["sd", "bn", "fault_tree", "bow_tie", "event_tree", "mcda", "decision_tree", "markov",
                      "equation_model", "fcm"], "declared": []}
    assert c.get("/api/contract").status_code == 422  # no contract yet
    cands = c.get("/api/contract/candidates", params={"model_type": "equation_model"}).json()
    assert [x["label"] for x in cands["inputs"]] == ["Depth", "Width", "Velocity"]
    r = c.post("/api/contract/init", json={"model_type": "equation_model"})
    assert r.status_code == 200 and r.json()["commit_sha"] and len(r.json()["result"]["inputs"]) == 2
    v1 = git.head_sha(project)
    assert c.get("/api/contract/types").json()["declared"] == ["equation_model"]
    assert c.get("/api/contract/check").json() == {"ready": True, "problems": []}

    r = c.post("/api/contract/input", json={"model_type": "equation_model", "node": "Velocity", "name": "speed",
                                            "valid_max": 2})
    assert r.status_code == 200 and r.json()["result"]["name"] == "speed"
    r = c.post("/api/contract/input", json={"model_type": "equation_model", "node": "Depth", "default": 2})
    assert r.json()["result"]["default"] == 2
    r = c.post("/api/contract/input", json={"model_type": "equation_model", "node": "Depth", "default": None})
    assert r.json()["result"]["default"] is None  # sent as null: cleared
    assert c.post("/api/contract/input", json={"model_type": "equation_model", "node": "Discharge"}).status_code == 422
    r = c.post("/api/contract/output", json={"model_type": "equation_model", "node": "Flow area"})
    assert r.json()["result"]["name"] == "flow_area"
    assert c.delete("/api/contract/equation_model/flow_area").json()["result"] == {"removed": "flow_area"}
    assert c.delete("/api/contract/equation_model/flow_area").status_code == 422

    shown = c.get("/api/contract").json()
    assert [i["name"] for i in shown["inputs"]] == ["depth", "width", "speed"] and shown["provenance"]["commit"]
    assert [i["name"] for i in c.get("/api/contract", params={"ref": v1}).json()["inputs"]] == ["depth", "width"]
    d = c.get("/api/contract/compare", params={"base": v1}).json()
    assert d["verdict"] == "compatible" and "input speed was added" in d["compatible"]

    before = _commits(project)
    r = c.post("/api/predict", json={"inputs": {"depth": 2, "speed": 1}}).json()
    assert r["outputs"]["discharge"]["value"] == pytest.approx(16) and r["provenance"]["commit"]
    assert c.post("/api/predict", json={"ref": v1}).json()["outputs"]["discharge"]["value"] == pytest.approx(Q)
    assert c.post("/api/predict", json={"inputs": {"nope": 1}}).status_code == 422
    assert c.post("/api/predict", json={"require": "approved"}).status_code == 422
    assert _commits(project) == before


def test_cli(project, tmp_path):
    from typer.testing import CliRunner

    from latris.cli.app import app

    runner = CliRunner()

    def run(*args: str, code: int = 0, stdin: str | None = None) -> str:
        out = runner.invoke(app, list(args), input=stdin)
        assert out.exit_code == code, out.output
        return out.output

    assert "no contract" in run("contract", "check", code=2)
    assert "Possible inputs" in run("contract", "available", "equation_model")
    out = run("contract", "init", "equation_model")
    assert "depth" in out and "discharge" in out and "drafted" in out
    v1 = git.head_sha(project)
    assert "fits the model" in run("contract", "check")
    run("contract", "input", "equation_model", "Velocity", "--name", "speed", "--max", "2", "-d", "mean velocity")
    run("contract", "input", "equation_model", "Depth", "--default", "2")
    run("contract", "output", "equation_model", "Flow area")
    shown = run("contract", "show")
    assert "speed" in shown and "flow_area" in shown and "m³/s" in shown
    assert "speed" not in run("contract", "show", "--ref", v1)
    assert "Compatible" in run("contract", "diff", v1)
    run("contract", "remove", "equation_model", "width")
    out = run("contract", "diff", v1, code=1)
    assert "Breaking" in out and "input width was removed" in out

    out = run("predict", "--set", "depth=250 cm", "-s", "speed=1")
    assert "20 m³/s" in out and "Nothing was recorded" in out and "depth = 2.5 m" in out
    assert "extrapolation" in run("predict", "--set", "speed=3")
    assert "10.8 m³/s" in run("predict", "--ref", v1)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"depth": 1}))
    data = json.loads(run("--json", "predict", "--inputs", str(inputs), "-s", "speed=2"))["result"]
    assert data["outputs"]["discharge"]["value"] == pytest.approx(16) and data["provenance"]["contract_hash"]
    data = json.loads(run("--json", "predict", "--inputs", "-", stdin='{"depth": 3}'))["result"]
    assert data["inputs"]["depth"]["value"] == 3
    assert "unknown input" in run("predict", "--set", "nope=1", code=2)
    run("predict", "--require", "approved", code=2)
    run("predict", "--inputs", "-", stdin="[1, 2]", code=2)
    run("contract", "input", "equation_model", "Depth", "--default", "none", "--required")
    assert "is required" in run("predict", code=2)


# ── regressions ──────────────────────────────────────────────────────


def test_an_output_is_given_in_the_contracts_units(project):
    contract.init("equation_model", root=project)
    v1 = git.head_sha(project)
    assert predict.predict(root=project)["outputs"]["discharge"] == {"value": pytest.approx(Q), "units": "m**3/s",
                                                                     "label": "Discharge"}
    # The model now works in litres a second; the contract still promises cubic metres.
    eq.set_formula("Discharge", "velocity * flow_area", "liter/s", root=project)
    assert eq.compute(eq.load(root=project))[contract.get("equation_model", root=project).outputs[0].target_id] \
        == pytest.approx(Q * 1000)
    assert contract.check(root=project) == []
    out = predict.predict(root=project)["outputs"]["discharge"]
    assert out["value"] == pytest.approx(Q) and out["units"] == "m**3/s"  # converted, not mislabelled
    assert contract.compare(v1, root=project)["verdict"] == "internal"
    # Changing something else about the output keeps the units it promised.
    contract.set_output("equation_model", "Discharge", description="what the channel carries", root=project)
    assert contract.get("equation_model", root=project).outputs[0].units == "m**3/s"

    # Units of another kind can't be converted: check says so, predict refuses, and the diff is breaking.
    eq.set_formula("Discharge", "velocity * flow_area / width", "m**2/s", root=project)
    (problem,) = contract.check(root=project)
    assert "output 'discharge' is in m**3/s, but Discharge is in m**2/s now" in problem
    with pytest.raises(ValueError, match="can't be run"):
        predict.predict(root=project)
    d = contract.compare(v1, root=project)
    assert d["verdict"] == "breaking" and "output discharge is in m**3/s" in d["breaking"][0]
    contract.set_output("equation_model", "Discharge", root=project)  # takes the model's units
    assert contract.get("equation_model", root=project).outputs[0].units == "m**2/s"
    assert contract.check(root=project) == []
    assert "output discharge changed from a value in m**3/s to a value in m**2/s" in contract.compare(
        v1, root=project)["breaking"]


def test_a_name_pointed_at_another_factor_is_a_breaking_change(project):
    contract.init("equation_model", root=project)
    v1, first = git.head_sha(project), contract.describe(root=project)["hash"]
    with pytest.raises(ValueError, match="already has an output called 'discharge', for Discharge"):
        contract.set_output("equation_model", "Flow area", name="discharge", root=project)  # not silently replaced
    assert contract.get("equation_model", root=project).outputs[0].units == "m**3/s"

    # Flow area and Discharge swap units, so the contract's text is identical but for the factor behind it.
    eq.set_formula("Flow area", "width * depth", "m**3/s", root=project)
    contract.remove("equation_model", "discharge", root=project)
    contract.set_output("equation_model", "Flow area", name="discharge", root=project)
    d = contract.compare(v1, root=project)
    assert d["verdict"] == "breaking" and "output discharge now reports a different factor" in d["breaking"]
    assert contract.describe(root=project)["hash"] != first

    new = contract.get("equation_model", root=project)
    same_text = new.model_copy(update={"outputs": [new.outputs[0].model_copy(update={"target_id": "other"})]})
    assert contract.contract_hash(same_text) != contract.contract_hash(new)
    inputs = new.model_copy(update={"inputs": [new.inputs[0].model_copy(update={"target_id": "other"}),
                                               *new.inputs[1:]]})
    assert contract.contract_hash(inputs) != contract.contract_hash(new)
    breaking: list[str] = []
    contract._compare_inputs(new, inputs, breaking, [])
    assert breaking == [f"input {new.inputs[0].name} now sets a different factor"]


def test_a_measure_of_a_run_has_its_own_units(system):
    contract.init("sd", root=system)
    when, _ = contract.set_output("sd", "PM2.5 Load", name="peak_at", metric="peak-time", root=system)
    total, _ = contract.set_output("sd", "PM2.5 Load", name="load_years", metric="total", root=system)
    emitted, _ = contract.set_output("sd", "Emission", name="emitted", metric="total", root=system)
    mean, _ = contract.set_output("sd", "PM2.5 Load", name="mean_load", metric="mean", root=system)
    assert (when.units, total.units, emitted.units, mean.units) == ("year", "tonne * year", "tonne", "tonne")
    assert contract.check("sd", root=system) == []
    out = predict.predict(model_type="sd", root=system)["outputs"]
    assert out["peak_at"]["units"] == "year" and 0 <= out["peak_at"]["value"] <= 10

    with pytest.raises(ValueError, match="at:1e\\+09 is outside the time the model runs over"):
        contract.set_output("sd", "PM2.5 Load", name="later", metric="at:1e9", root=system)
    contract.set_output("sd", "PM2.5 Load", name="midway", metric="at:5", root=system)
    # A contract written before the check (or a run since shortened) is caught by `contract check`.
    paths = eq.require_project(system)
    c = contract.get("sd", root=system)
    c.outputs = [o.model_copy(update={"metric": "at:1e9"}) if o.name == "midway" else
                 o.model_copy(update={"units": "tonne"}) if o.name == "peak_at" else o for o in c.outputs]
    contract._save(paths, c, "an older contract")
    problems = contract.check("sd", root=system)
    assert any("'midway'" in p and "outside the time" in p for p in problems)
    assert any("'peak_at' is in tonne, but PM2.5 Load is in year now" in p for p in problems)


def test_a_series_is_converted_too_and_hidden_stocks_are_not_offered(system):
    from latris.operations import sd as sd_ops

    hidden = sd_ops.compile_project(root=system).hidden
    assert hidden  # the example smooths a variable: SMOOTH's own stocks are not the modeller's
    offered = contract.candidates("sd", root=system)
    assert not hidden & {c["target_id"] for c in offered["inputs"] + offered["outputs"]}

    c, _ = contract.init("sd", root=system)
    name = next(o.name for o in c.outputs if o.units == "tonne")
    tonnes = predict.predict(model_type="sd", root=system)["outputs"][name]["series"]["values"]
    c.outputs = [o.model_copy(update={"units": "kilogram"}) if o.name == name else o for o in c.outputs]
    contract._save(eq.require_project(system), c, "the caller reads kilograms")
    out = predict.predict(model_type="sd", root=system)["outputs"][name]
    assert out["units"] == "kilogram" and out["series"]["values"] == pytest.approx([v * 1000 for v in tonnes])


def test_a_model_type_never_names_a_file(project, tmp_path):
    from fastapi.testclient import TestClient

    from latris.repo.layout import ProjectPaths
    from latris.server.app import create_app

    contract.init("equation_model", root=project)
    secret = tmp_path / "secret.yaml"
    secret.write_text("password: hunter2\n")
    c = TestClient(create_app(project_root=project))
    up = "../../../../secret"
    for r in (c.get("/api/contract/check", params={"model_type": up}),
              c.get("/api/contract", params={"model_type": up}),
              c.get("/api/contract/candidates", params={"model_type": up}),
              c.post("/api/contract/init", json={"model_type": up}),
              c.post("/api/contract/output", json={"model_type": up, "node": "Discharge"}),
              c.post("/api/predict", json={"model_type": up})):
        assert r.status_code == 422, r.text
        assert "hunter2" not in r.text and "password" not in r.text
    assert "unknown model type" in c.get("/api/contract/check", params={"model_type": "zzz"}).json()["detail"]
    for bad in (up, "a/b", "..", "", "Equation Model", "x.yaml"):
        with pytest.raises(ValueError, match="not a model type"):
            ProjectPaths(project).contract_path(bad)
    assert ProjectPaths(project).contract_path("equation_model").name == "equation_model.yaml"


def test_predict_refuses_a_malformed_value_and_reads_an_empty_ref_as_none(project):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    contract.init("equation_model", root=project)
    c = TestClient(create_app(project_root=project))
    r = c.post("/api/predict", json={"inputs": {"depth": {"value": 2, "units": 5}}})
    assert r.status_code == 422 and "units must be text" in r.json()["detail"]
    assert c.post("/api/predict", json={"inputs": {"depth": {"value": 2, "units": ["cm"]}}}).status_code == 422
    assert c.post("/api/predict", json={"inputs": {"depth": True}}).status_code == 422
    r = c.post("/api/predict", json={"ref": "", "inputs": {"depth": {"value": 200, "units": "cm"}}})
    assert r.status_code == 200 and r.json()["provenance"]["ref"] is None  # the working folder, not a pin
    assert r.json()["outputs"]["discharge"]["value"] == pytest.approx(0.9 * 8 * 2)
    assert c.get("/api/contract", params={"ref": ""}).status_code == 200
