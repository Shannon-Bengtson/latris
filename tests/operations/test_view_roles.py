"""Tests for view role operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_roles as role_ops
from latris.operations.init import init_project


@pytest.fixture
def project(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    a, _ = node_ops.add_node("Population", kind="variable", root=root)
    b, _ = node_ops.add_node("Birth Rate", kind="variable", root=root)
    e1, _ = edge_ops.add_edge(a.id, b.id, kind="causal", root=root)
    monkeypatch.chdir(root)
    return root, a, b, e1


def test_set_role(project):
    root, a, _, _ = project
    target_id, sha = role_ops.set_role(a.id, "cld", "stock", root=root)
    assert target_id == a.id
    assert sha

    roles = role_ops.get_roles("cld", root=root)
    assert len(roles.entries) == 1
    assert roles.entries[0].target_id == a.id
    assert roles.entries[0].value == "stock"


def test_set_role_upserts(project):
    root, a, _, _ = project
    role_ops.set_role(a.id, "cld", "stock", root=root)
    role_ops.set_role(a.id, "cld", "auxiliary", root=root)

    roles = role_ops.get_roles("cld", root=root)
    assert len(roles.entries) == 1
    assert roles.entries[0].value == "auxiliary"


def test_set_multiple_roles(project):
    root, a, b, _ = project
    role_ops.set_role(a.id, "cld", "stock", root=root)
    role_ops.set_role(b.id, "cld", "flow", root=root)

    roles = role_ops.get_roles("cld", root=root)
    assert len(roles.entries) == 2


def test_get_roles_empty(project):
    root, _, _, _ = project
    roles = role_ops.get_roles("cld", root=root)
    assert len(roles.entries) == 0


def test_role_resolves_by_label(project):
    root, a, _, _ = project
    target_id, _ = role_ops.set_role("Population", "cld", "stock", root=root)
    assert target_id == a.id
