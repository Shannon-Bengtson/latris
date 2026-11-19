

def test_export_spec_round_trips_through_build(tmp_path, git_identity, monkeypatch):
    """`latris export spec` prints what `latris build --spec` reads back."""
    import json

    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.operations.build import build_from_spec, load_spec
    from latris.operations.init import init_project
    from latris.operations.project import update_selected_models
    from latris.testing import build_example

    src = build_example("mcda", tmp_path / "src")
    monkeypatch.chdir(src)
    runner = CliRunner()
    text = runner.invoke(app, ["export", "spec"]).stdout
    spec = json.loads(text)
    assert spec["model_type"] == "mcda" and spec["mcda"]["criteria"]
    envelope = json.loads(runner.invoke(app, ["--json", "export", "spec"]).stdout.strip().splitlines()[-1])
    assert envelope["result"] == spec

    dest = tmp_path / "dest"
    init_project(dest, statement="Q?")
    update_selected_models(["mcda"], root=dest)
    build_from_spec(load_spec(text), root=dest)
    monkeypatch.chdir(dest)
    again = json.loads(runner.invoke(app, ["export", "spec"]).stdout)
    assert again["mcda"] == spec["mcda"]


def test_results_show_json_gives_the_report_section(tmp_path, git_identity, monkeypatch):
    """What a chat tool returns: the recorded result, its report section and the claims it supports."""
    import json

    from typer.testing import CliRunner

    from latris.cli.app import app
    from latris.testing import build_example

    monkeypatch.chdir(build_example("system", tmp_path / "s"))
    runner = CliRunner()
    listed = json.loads(runner.invoke(app, ["--json", "results", "list"]).stdout.strip().splitlines()[-1])["result"]
    sim = next(r for r in listed if r["kind"] == "sd-simulation")
    shown = json.loads(runner.invoke(app, ["--json", "results", "show", sim["run_id"]]).stdout.strip().splitlines()[-1])
    out = shown["result"]
    assert out["report"].startswith("### Simulation") and "|" in out["report"]
    assert out["claims"] and out["result"]["scenarios"]
