"""CLI tests for the `story` command group."""

from __future__ import annotations

from typer.testing import CliRunner

from latris.ai import proposals as p
from latris.ai.adapters.base import ChatResult
from latris.ai.adapters.mock_adapter import MockAdapter
from latris.cli.app import app
from latris.operations.commit import auto_commit
from latris.operations.edges import add_edge
from latris.operations.findings import record_new_finding
from latris.operations.init import init_project
from latris.operations.nodes import add_node
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.project import ProjectFoundation


def _project(tmp_path):
    root = tmp_path / "proj"
    init_project(root, statement="What drives water quality decline?")
    paths = ProjectPaths(root)
    f = load_model(ProjectFoundation, paths.project_yaml)
    f.selected_model_types = ["cld"]
    f.name = "Coastal"
    dump_model(f, paths.project_yaml)
    auto_commit(root, subject="cld", paths=[paths.project_yaml])
    a, _ = add_node("Nutrient load", kind="variable", root=root)
    b, _ = add_node("Algal bloom", kind="variable", root=root)
    e1, _ = add_edge(a.id, b.id, kind="causal", root=root)
    e2, _ = add_edge(b.id, a.id, kind="causal", root=root)
    record_new_finding(
        "loop",
        category="structure",
        model_type="cld",
        payload={"node_ids": [a.id, b.id], "edge_ids": [e1.id, e2.id]},
        root=root,
    )
    return root


def test_story_draft_export_and_list(tmp_path, git_identity, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()

    r = runner.invoke(app, ["story", "draft", "--model", "cld"])
    assert r.exit_code == 0, r.output
    assert "drafted" in r.output

    out = tmp_path / "story.html"
    r2 = runner.invoke(app, ["story", "export", "--model", "cld", "-o", str(out)])
    assert r2.exit_code == 0, r2.output
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "Coastal" in html

    r3 = runner.invoke(app, ["story", "list"])
    assert r3.exit_code == 0, r3.output
    assert "cld" in r3.output


def _mock_prose(monkeypatch):
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.shared().register_default(
        response_cls=p.InterpretProseResult,
        result=ChatResult(
            parsed=p.InterpretProseResult(prose="(mock) prose."),
            raw="(mock)",
            model_id="mock-model",
        ),
    )


def test_story_list_empty(tmp_path, git_identity, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    r = runner.invoke(app, ["story", "list"])
    assert r.exit_code == 0, r.output
    assert "no stories" in r.output


def test_story_show(tmp_path, git_identity, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    runner.invoke(app, ["story", "draft", "--model", "cld"])

    r = runner.invoke(app, ["story", "show", "--model", "cld"])
    assert r.exit_code == 0, r.output
    assert "Coastal" in r.output
    assert "hook" in r.output


def test_story_show_missing_errors(tmp_path, git_identity, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    r = runner.invoke(app, ["story", "show", "--model", "cld"])
    assert r.exit_code == 1
    assert "no story" in r.output


def test_story_generate_prose_and_set(tmp_path, git_identity, monkeypatch):
    _mock_prose(monkeypatch)
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    draft = runner.invoke(app, ["story", "draft", "--model", "cld"])
    assert draft.exit_code == 0, draft.output
    from latris.operations.story import load_story

    beat_id = load_story(root=root).docs[0].beats[0].id

    gen = runner.invoke(app, ["story", "generate-prose", beat_id, "--model", "cld"])
    assert gen.exit_code == 0, gen.output
    assert "generated" in gen.output

    setp = runner.invoke(app, ["story", "set-prose", beat_id, "Human prose.", "--model", "cld"])
    assert setp.exit_code == 0, setp.output
    assert "updated" in setp.output


def test_story_generate_all(tmp_path, git_identity, monkeypatch):
    _mock_prose(monkeypatch)
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    runner.invoke(app, ["story", "draft", "--model", "cld"])

    r = runner.invoke(app, ["story", "generate-all", "--model", "cld"])
    assert r.exit_code == 0, r.output
    assert "done" in r.output


def test_story_generate_all_missing_errors(tmp_path, git_identity, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    r = runner.invoke(app, ["story", "generate-all", "--model", "cld"])
    assert r.exit_code == 1
    assert "no story" in r.output


def test_story_export_to_stdout(tmp_path, git_identity, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    runner.invoke(app, ["story", "draft", "--model", "cld"])

    r = runner.invoke(app, ["story", "export", "--model", "cld"])
    assert r.exit_code == 0, r.output
    assert "<!DOCTYPE html>" in r.output
