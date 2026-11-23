"""Declared analyses for generated forms: the catalog, the choices, and running one (routes/analyses.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from latris.server.app import create_app


def test_catalog_lists_a_types_analyses_with_input_hints(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    analyses = c.get("/api/analyses", params={"model_type": "sd"}).json()["analyses"]
    kinds = {a["analysis"] for a in analyses}
    assert {"simulate", "monte_carlo", "compare", "sensitivity", "loops"} <= kinds
    compare = next(a for a in analyses if a["analysis"] == "compare")
    props = compare["analysis_schema"]["properties"]
    assert props["scenarios"]["x-input"] == "scenarios" and props["apply_to_all"]["x-input"] == "assignments"
    assert props["variable"]["x-input"] == "factor" and props["reference"]["x-input"] == "arm"
    assert props["scenarios"]["description"]  # described, as for the chat tools


def test_catalog_includes_analysis_layers(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    dag = c.get("/api/analyses", params={"model_type": "dag"}).json()["analyses"]
    est = next(a for a in dag if a["analysis"] == "dag_estimate")
    assert est["needs_dataset"] is True
    assert est["analysis_schema"]["properties"]["dataset"]["x-input"] == "dataset"


def test_choices_are_the_types_factors_and_scenarios(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    ch = c.get("/api/analyses/choices", params={"model_type": "sd"}).json()
    assert "Water" in {f["label"] for f in ch["factors"]}
    assert ch["states"] == {} and isinstance(ch["scenarios"], list) and isinstance(ch["datasets"], list)


def test_run_records_the_analysis(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    r = c.post("/api/analyses/run", json={"kind": "simulate", "settings": {"final_time": 5}})
    assert r.status_code == 200, r.text
    run_id = r.json()["result"]["run_id"]
    assert run_id in {row["run"]["id"] for row in c.get("/api/results").json()["results"]}


def test_run_refuses_options_the_analysis_does_not_take(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    r = c.post("/api/analyses/run", json={"kind": "simulate", "treatment": "Water"})
    assert r.status_code == 422 and "treatment" in r.json()["detail"]



def test_choices_give_a_networks_states_by_label(two_node_project_root):
    from latris.operations.bn import set_state_space

    set_state_space("Price", ["low", "high"], root=two_node_project_root)
    c = TestClient(create_app(project_root=two_node_project_root))
    ch = c.get("/api/analyses/choices", params={"model_type": "bn"}).json()
    assert ch["states"] == {"Price": ["low", "high"]}
    assert "Price" in {f["label"] for f in ch["factors"]}


def test_run_says_what_is_wrong_with_the_kind(sd_bathtub_root):
    c = TestClient(create_app(project_root=sd_bathtub_root))
    r = c.post("/api/analyses/run", json={})
    assert r.status_code == 422 and "'kind'" in r.json()["detail"]
    assert c.post("/api/analyses/run", json={"kind": 3}).status_code == 422
    r = c.post("/api/analyses/run", json={"kind": "no_such_analysis"})
    assert r.status_code == 422 and "no analysis of kind 'no_such_analysis'" in r.json()["detail"]


def test_a_stray_lookup_error_is_logged(sd_bathtub_root, caplog):
    from latris.operations.errors import NotFoundError

    app = create_app(project_root=sd_bathtub_root)

    @app.get("/api/_test/stray")
    def stray() -> None:
        [][0]  # noqa: B018 — a bug, not a deliberate not-found

    @app.get("/api/_test/missing")
    def missing() -> None:
        raise NotFoundError("no such run")

    c = TestClient(app)
    with caplog.at_level("WARNING", logger="latris.server"):
        assert c.get("/api/_test/missing").status_code == 404
        assert not caplog.records
        assert c.get("/api/_test/stray").status_code == 404
    assert "IndexError answered 404 on GET /api/_test/stray" in caplog.text
