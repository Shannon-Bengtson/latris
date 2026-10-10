"""Tests for report pack definitions and pack-filtered markdown (M15)."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters import markdown as md_exporter
from latris.exporters.packs import PACKS, get_pack
from latris.operations import nodes as node_ops
from latris.operations.init import init_project


def test_all_packs_defined():
    assert set(PACKS.keys()) == {"client", "audit", "review", "workshop", "publication"}


def test_audit_pack_includes_all_sections():
    pack = get_pack("audit")
    assert "foundation" in pack.sections
    assert "challenges" in pack.sections
    assert "predictions" in pack.sections
    assert "signoffs" in pack.sections


def test_unknown_pack_raises():
    with pytest.raises(KeyError, match="Unknown pack"):
        get_pack("nonexistent")


def test_publication_pack_excludes_challenges():
    pack = get_pack("publication")
    assert "challenges" not in pack.sections


def test_md_render_with_client_pack(tmp_path: Path, git_identity, monkeypatch):
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    node_ops.add_node("Price", kind="variable", root=root)
    monkeypatch.chdir(root)

    from latris.repo.layout import ProjectPaths

    paths = ProjectPaths(root)

    # Full render has challenges section
    full_md = md_exporter.render(paths)
    assert "## Challenges" in full_md

    # Client pack should not have challenges
    client_md = md_exporter.render(paths, pack="client")
    assert "## Challenges" not in client_md
    assert "## Nodes" in client_md

    # Publication pack should not have assumptions
    pub_md = md_exporter.render(paths, pack="publication")
    assert "## Assumptions" not in pub_md
    assert "## References" in pub_md
