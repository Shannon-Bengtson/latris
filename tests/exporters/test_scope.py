"""Per-formalism scoping of report exporters (markdown + word).

When a report is scoped to a ``model_type`` the substrate is filtered to that
formalism's view (via mappings) and findings are filtered to that model type.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.exporters import markdown, word
from latris.exporters._scope import view_member_ids
from latris.operations import edges as edge_ops
from latris.operations import findings as finding_ops
from latris.operations import mappings as mapping_ops
from latris.operations import nodes as node_ops
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def two_formalism_project(tmp_path: Path, git_identity):
    """A project whose substrate is split across two formalisms (cld, dag)."""
    root = tmp_path / "demo"
    init_project(root, statement="Does X cause Y?")
    cld_a, _ = node_ops.add_node("Nutrients", kind="variable", root=root)
    cld_b, _ = node_ops.add_node("Algae", kind="variable", root=root)
    dag_c, _ = node_ops.add_node("Rainfall", kind="variable", root=root)
    e_cld, _ = edge_ops.add_edge(cld_a.id, cld_b.id, kind="causal", root=root)

    mapping_ops.map_to_view(cld_a.id, "cld", root=root)
    mapping_ops.map_to_view(cld_b.id, "cld", root=root)
    mapping_ops.map_to_view(e_cld.id, "cld", root=root)
    mapping_ops.map_to_view(dag_c.id, "dag", root=root)

    finding_ops.record_new_finding("Nutrients drive algae blooms", "structure", "cld", root=root)
    finding_ops.record_new_finding("Rainfall is exogenous", "structure", "dag", root=root)
    return root, cld_a, cld_b, dag_c


def test_view_member_ids_filters_to_formalism(two_formalism_project):
    root, cld_a, cld_b, dag_c = two_formalism_project
    members = view_member_ids(ProjectPaths(root), "cld")
    assert members is not None
    assert cld_a.id in members
    assert cld_b.id in members
    assert dag_c.id not in members


def test_view_member_ids_none_means_no_scoping(two_formalism_project):
    root, *_ = two_formalism_project
    assert view_member_ids(ProjectPaths(root), None) is None
    assert view_member_ids(ProjectPaths(root), "system_map") is None
    # A formalism with no mappings also yields None (render whole substrate).
    assert view_member_ids(ProjectPaths(root), "fcm") is None


def test_markdown_scopes_substrate_and_findings(two_formalism_project):
    root, cld_a, cld_b, dag_c = two_formalism_project
    # Scope to the structured sections — the project-level history prose
    # (built from git commit subjects) legitimately references all nodes.
    out = markdown.render(ProjectPaths(root), sections=["nodes", "findings"], model_type="cld")
    assert "Nutrients" in out
    assert "Algae" in out
    assert "Rainfall" not in out  # dag-only node excluded
    assert "Nutrients drive algae blooms" in out
    assert "Rainfall is exogenous" not in out  # dag-only finding excluded


def test_markdown_unscoped_includes_everything(two_formalism_project):
    root, *_ = two_formalism_project
    out = markdown.render(ProjectPaths(root))
    assert "Nutrients" in out
    assert "Rainfall" in out
    assert "Rainfall is exogenous" in out


def test_word_scopes_substrate_and_findings(two_formalism_project):
    root, *_ = two_formalism_project
    doc = word.render(ProjectPaths(root), sections=["nodes", "findings"], model_type="cld")
    text = "\n".join(p.text for p in doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            text += "\n" + " | ".join(c.text for c in row.cells)
    assert "Nutrients" in text
    assert "Rainfall" not in text
    assert "Nutrients drive algae blooms" in text
    assert "Rainfall is exogenous" not in text
