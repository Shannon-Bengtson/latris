"""Test fixtures.

Hermetic git identity: tests that commit use env-var overrides so they don't
depend on the developer's global ``~/.gitconfig``. ``GIT_AUTHOR_*`` and
``GIT_COMMITTER_*`` are honoured by git directly, ahead of config.

Shared template projects: ``init_project`` plus a handful of nodes/edges is
~1.5-2.5s of git work, repeated for every test in many files. The
``_template_*_root`` fixtures (session-scoped) build each common shape
once; the corresponding ``*_project_root`` fixtures (function-scoped)
``shutil.copytree`` the template into the test's ``tmp_path`` in tens of
milliseconds. Test files needing bespoke shapes can call
:func:`build_with_template_identity` directly in module-scoped fixtures.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

T = TypeVar("T")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --slow flag to opt in to slow tests."""
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="include tests marked @pytest.mark.slow",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests marked @pytest.mark.slow unless --slow is given."""
    if config.getoption("--slow"):
        return
    skip_slow = pytest.mark.skip(reason="use --slow to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture
def git_identity(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Provide a usable git identity via env vars; yields (name, email)."""
    name = "Test Runner"
    email = "test-runner@example.invalid"
    monkeypatch.setenv("GIT_AUTHOR_NAME", name)
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", email)
    monkeypatch.setenv("GIT_COMMITTER_NAME", name)
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", email)
    return name, email


@pytest.fixture
def no_git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force-clear any inherited identity so the guard can be exercised."""
    for var in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(var, raising=False)


# ── Template projects ────────────────────────────────────────────────


def build_with_template_identity(builder: Callable[[], T]) -> T:
    """Run ``builder`` with a fixed git identity in env vars.

    Session-scoped template fixtures can't depend on the function-scoped
    ``git_identity`` fixture, so they call this helper to set the env vars
    inline for the duration of the build. Per-test commits made later use
    the test's own ``git_identity`` fixture (because the function-scoped
    clone fixtures depend on it).
    """
    saved: dict[str, str | None] = {}
    for var, val in [
        ("GIT_AUTHOR_NAME", "Template Builder"),
        ("GIT_AUTHOR_EMAIL", "template@example.invalid"),
        ("GIT_COMMITTER_NAME", "Template Builder"),
        ("GIT_COMMITTER_EMAIL", "template@example.invalid"),
    ]:
        saved[var] = os.environ.get(var)
        os.environ[var] = val
    try:
        return builder()
    finally:
        for var, prev in saved.items():
            if prev is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev


def clone_project(template: Path, dest: Path) -> Path:
    """Copy a template project to ``dest`` and return ``dest``."""
    shutil.copytree(template, dest)
    return dest


@pytest.fixture(scope="session")
def _template_empty_project_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Bare initialised project. Statement ``"Q?"``, dir name ``"proj"``."""
    from latris.operations.init import init_project

    def build() -> Path:
        root = tmp_path_factory.mktemp("tpl_empty") / "proj"
        init_project(root, statement="Q?")
        return root

    return build_with_template_identity(build)


@pytest.fixture(scope="session")
def _template_two_node_project_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """init + Price + Demand + (Price → Demand). Statement ``"Q?"``, dir ``"proj"``."""
    from latris.operations.edges import add_edge
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node

    def build() -> Path:
        root = tmp_path_factory.mktemp("tpl_2n1e") / "proj"
        init_project(root, statement="Q?")
        a, _ = add_node("Price", kind="variable", root=root)
        b, _ = add_node("Demand", kind="variable", root=root)
        add_edge(a.id, b.id, kind="causal", root=root)
        return root

    return build_with_template_identity(build)


@pytest.fixture(scope="session")
def _template_triangle_project_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """init + Variable A,B,C + (A→B, B→C, C→A). Statement ``"Test Q?"``, dir ``"proj"``."""
    from latris.operations.edges import add_edge
    from latris.operations.init import init_project
    from latris.operations.nodes import add_node

    def build() -> Path:
        root = tmp_path_factory.mktemp("tpl_triangle") / "proj"
        init_project(root, statement="Test Q?")
        a, _ = add_node("Variable A", kind="variable", root=root)
        b, _ = add_node("Variable B", kind="variable", root=root)
        c, _ = add_node("Variable C", kind="variable", root=root)
        add_edge(a.id, b.id, kind="causal", root=root)
        add_edge(b.id, c.id, kind="causal", root=root)
        add_edge(c.id, a.id, kind="causal", root=root)
        return root

    return build_with_template_identity(build)


@pytest.fixture
def empty_project_root(_template_empty_project_root: Path, tmp_path: Path, git_identity) -> Path:
    """Function-scoped clone of an empty initialised project."""
    return clone_project(_template_empty_project_root, tmp_path / "proj")


@pytest.fixture
def two_node_project_root(_template_two_node_project_root: Path, tmp_path: Path, git_identity) -> Path:
    """Function-scoped clone with Price + Demand + (Price → Demand)."""
    return clone_project(_template_two_node_project_root, tmp_path / "proj")


@pytest.fixture
def triangle_project_root(_template_triangle_project_root: Path, tmp_path: Path, git_identity) -> Path:
    """Function-scoped clone with three nodes + three edges forming a triangle."""
    return clone_project(_template_triangle_project_root, tmp_path / "proj")
