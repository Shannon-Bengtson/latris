from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations.init import ProjectAlreadyExistsError, init_project
from latris.repo import git
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import load_model
from latris.schema import ProjectFoundation


def test_init_scaffolds_full_layout(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "demo"
    paths = init_project(
        root,
        statement="Does X cause Y in context Z?",
    )

    # Every canonical path from the layout exists.
    assert paths.project_yaml.is_file()
    assert paths.version_file.is_file()
    assert paths.references_bib.is_file()
    assert paths.research_notes_md.is_file()
    assert paths.conceptual_yaml.is_file()
    assert paths.mappings_yaml.is_file()
    assert paths.descriptions_yaml.is_file()
    assert paths.confidence_yaml.is_file()
    assert paths.view_attribute_path("cld", "polarity").is_file()
    assert paths.evidence_links_yaml.is_file()
    assert paths.view_yaml("cld").is_file()
    assert paths.view_yaml("dag").is_file()
    for log in (
        paths.assumptions_yaml,
        paths.decisions_yaml,
        paths.signoffs_yaml,
        paths.sessions_yaml,
        paths.questions_yaml,
        paths.exclusions_yaml,
        paths.predictions_yaml,
        paths.challenges_yaml,
    ):
        assert log.is_file(), log

    assert paths.interactions_jsonl.is_file()
    assert paths.ai_project_context_md.is_file()
    assert paths.reports_draft_md.is_file()

    # M11: elicitation, data, analysis stubs
    assert paths.elicitations_yaml.is_file()
    assert paths.elicitations_dir.is_dir()
    assert paths.data_datasets_yaml.is_file()
    assert paths.data_dir.is_dir()
    assert paths.data_files_dir.is_dir()
    assert paths.analysis_runs_jsonl.is_file()
    assert paths.analysis_dir.is_dir()
    assert paths.analysis_outputs_dir.is_dir()

    assert (root / ".gitignore").is_file()
    assert (root / ".gitattributes").is_file()
    assert (root / ".git").is_dir()


def test_init_writes_correct_foundation(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "demo"
    init_project(root, statement="Raise subscription price.")
    paths = ProjectPaths(root)
    loaded = load_model(ProjectFoundation, paths.project_yaml)
    assert loaded.statement == "Raise subscription price."
    assert paths.version_file.read_text(encoding="utf-8").strip() == "6"


def test_init_creates_initial_commit(tmp_path: Path, git_identity: tuple[str, str]) -> None:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    name, email = git.head_author(root)
    assert name == git_identity[0]
    assert email == git_identity[1]
    # exactly one commit so far
    count = git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip()
    assert count == "1"


def test_init_refuses_non_empty_dir(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "sentinel").write_text("keep me", encoding="utf-8", newline="")
    with pytest.raises(ProjectAlreadyExistsError):
        init_project(root, statement="Q?")


def test_init_accepts_existing_empty_dir(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    init_project(root, statement="Q?")
    assert (root / ".git").is_dir()


def test_init_records_project_name(tmp_path: Path, git_identity) -> None:
    """init_project(name=X) should write X to ProjectFoundation.name."""
    root = tmp_path / "demo"
    init_project(root, statement="Q?", name="Coastal Erosion Model")
    foundation = load_model(ProjectFoundation, ProjectPaths(root).project_yaml)
    assert foundation.name == "Coastal Erosion Model"


def test_init_default_name_is_empty(tmp_path: Path, git_identity) -> None:
    """Backwards-compat: existing callers that don't pass name still work."""
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    foundation = load_model(ProjectFoundation, ProjectPaths(root).project_yaml)
    assert foundation.name == ""


def test_init_without_identity_fails_before_touching_fs(
    tmp_path: Path, no_git_identity, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Also fool the config probe by pointing HOME/XDG to an empty dir so any
    # real global config isn't read.
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / "xdg"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(fake_home / "nonexistent-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(fake_home / "nonexistent-system"))

    root = tmp_path / "demo"
    with pytest.raises(git.IdentityError):
        init_project(root, statement="Q?")
    assert not root.exists()  # fs untouched on identity refusal
