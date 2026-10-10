"""CLI tests for the top-level `init` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import ProjectFoundation

runner = CliRunner()


def test_init_happy_relative_name(tmp_path: Path, git_identity, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init", "newproj", "-q", "What drives X?"])
    assert r.exit_code == 0, r.output
    assert "initialised" in r.output
    root = tmp_path / "newproj"
    assert (root / ".git").exists()
    foundation = load_model(ProjectFoundation, ProjectPaths(root).project_yaml)
    assert foundation.statement == "What drives X?"
    # Display name defaults to the directory basename.
    assert foundation.name == "newproj"


def test_init_custom_display_name(tmp_path: Path, git_identity, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(
        app, ["init", "proj2", "-q", "Q?", "--name", "Coastal Water Quality"]
    )
    assert r.exit_code == 0, r.output
    foundation = load_model(
        ProjectFoundation, ProjectPaths(tmp_path / "proj2").project_yaml
    )
    assert foundation.name == "Coastal Water Quality"


def test_init_absolute_path(tmp_path: Path, git_identity, monkeypatch):
    target = tmp_path / "abs_proj"
    r = runner.invoke(app, ["init", str(target), "-q", "Q?"])
    assert r.exit_code == 0, r.output
    assert (target / ".git").exists()


def test_init_missing_question_errors(tmp_path: Path, git_identity, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # --question is a required option; omitting it is a usage error.
    r = runner.invoke(app, ["init", "noq"])
    assert r.exit_code != 0


def test_init_existing_nonempty_dir_errors(tmp_path: Path, git_identity, monkeypatch):
    monkeypatch.chdir(tmp_path)
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "stray.txt").write_text("hi", encoding="utf-8")
    r = runner.invoke(app, ["init", "taken", "-q", "Q?"])
    assert r.exit_code == 1
    assert "error:" in r.output
    assert "already exists" in r.output


def test_init_without_identity_errors(tmp_path: Path, no_git_identity, monkeypatch):
    # Point git's config probes at empty locations so no real global identity
    # is found, forcing the IdentityError branch.
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / "xdg"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(fake_home / "nonexistent-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(fake_home / "nonexistent-system"))
    monkeypatch.chdir(tmp_path)

    r = runner.invoke(app, ["init", "noident", "-q", "Q?"])
    assert r.exit_code == 1
    assert "identity error:" in r.output
    assert not (tmp_path / "noident").exists()
