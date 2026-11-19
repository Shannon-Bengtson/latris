"""Building into a project that already has some of the spec: refuse (default) or reuse; and the dry run."""

from __future__ import annotations

import pytest

from latris.operations.build import build_from_spec, load_spec, preview_build
from latris.operations.share_link import export_spec
from latris.repo import git

SPEC = """
factors:
  - label: Water
    description: From the spec
  - label: Overflow
links:
  - from: Water
    to: Overflow
    polarity: "+"
sources:
  - key: smith2020
    title: Bathtubs
"""


def _spec():
    return load_spec(SPEC)


def test_refuse_names_what_is_already_there(sd_bathtub_root):
    with pytest.raises(ValueError, match="factor already in the project: Water"):
        build_from_spec(_spec(), root=sd_bathtub_root)


def test_reuse_keeps_what_is_there_and_adds_the_rest(sd_bathtub_root):
    from latris.operations.attributes import get_attribute
    from latris.operations.nodes import list_nodes

    water = next(n for n in list_nodes(root=sd_bathtub_root) if n.label == "Water")
    before = get_attribute(water.id, "description", root=sd_bathtub_root)
    r = build_from_spec(_spec(), existing="reuse", root=sd_bathtub_root)
    assert (r.factors, r.reused_factors, len(r.links), r.sources) == (1, 1, 1, 1)
    labels = [n.label for n in list_nodes(root=sd_bathtub_root)]
    assert labels.count("Water") == 1 and "Overflow" in labels
    after = get_attribute(water.id, "description", root=sd_bathtub_root)
    assert after == (before or "From the spec")  # theirs only fills a gap


def test_reimporting_your_own_export_reuses_everything(sd_bathtub_root):
    _, spec = export_spec(model_type="sd", root=sd_bathtub_root)
    spec.analyses = []
    with pytest.raises(ValueError):
        build_from_spec(spec, root=sd_bathtub_root)  # refused as before
    r = build_from_spec(spec, existing="reuse", root=sd_bathtub_root)
    assert r.factors == 0 and not r.links and r.reused_factors == len(spec.factors) and r.reused_links == len(spec.links)
    assert r.citations == 0  # every citation was already there


def test_preview_changes_nothing_and_matches_the_build(sd_bathtub_root):
    head = git.head_sha(sd_bathtub_root)
    p = preview_build(_spec(), existing="reuse", root=sd_bathtub_root)
    assert git.head_sha(sd_bathtub_root) == head  # the project is untouched
    assert p.ok and p.result.factors == 1 and p.result.reused_factors == 1
    assert any(c["kind"] == "node_added" and "Overflow" in c["summary"] for c in p.changes)
    real = build_from_spec(_spec(), existing="reuse", root=sd_bathtub_root)
    assert (real.factors, real.reused_factors, len(real.links)) == (p.result.factors, p.result.reused_factors, len(p.result.links))


def test_preview_says_why_it_cannot_build(sd_bathtub_root):
    p = preview_build(_spec(), root=sd_bathtub_root)
    assert not p.ok and any("already in the project" in x for x in p.problems) and p.result is None


def test_routes_preview_then_build(sd_bathtub_root):
    from fastapi.testclient import TestClient

    from latris.server.app import create_app

    c = TestClient(create_app(project_root=sd_bathtub_root))
    spec = _spec().model_dump(mode="json", by_alias=True, exclude_none=True)
    refused = c.post("/api/build/preview", json={"spec": spec}).json()
    assert refused["ok"] is False and refused["problems"]
    p = c.post("/api/build/preview", json={"spec": spec, "existing": "reuse"}).json()
    assert p["ok"] and p["result"]["reused_factors"] == 1 and p["changes"]
    r = c.post("/api/build", json={"spec": spec, "existing": "reuse"})
    assert r.status_code == 200 and r.json()["commit_sha"]
