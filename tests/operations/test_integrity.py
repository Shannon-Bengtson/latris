"""Referential integrity: removals clean up after themselves, duplicates are refused,
and ``check_integrity`` finds what a hand edit or bad merge can break."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import build as build_ops
from latris.operations.challenges import open_challenge
from latris.operations.edges import DuplicateEdgeError, add_edge, list_edges, remove_edge
from latris.operations.handover import handover_check
from latris.operations.init import init_project
from latris.operations.integrity import check_integrity, remove_dangling_rows
from latris.operations.nodes import add_node, get_node, remove_node, rename_node
from latris.operations.project import update_selected_models
from latris.operations.references import add_reference, set_source_snapshot
from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_raw, load_raw
from latris.schema.references import SNAPSHOT_EXTRACT_MAX

SPEC = """
outcome: Departures
factors:
  - {label: Workload, description: Hours asked of each volunteer.}
  - {label: Burnout, description: Exhaustion from the work.}
  - label: Departures
links:
  - {from: Workload, to: Burnout, polarity: "+", reason: More hours wear people down., sources: [smith2024],
     confidence: high}
  - {from: Burnout, to: Departures, polarity: "+"}
sources:
  - {key: smith2024, title: Burnout among community volunteers}
"""


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "vol"
    init_project(root, statement="Why do volunteers leave?")
    update_selected_models(["cld"], root=root)
    build_ops.build_from_spec(build_ops.load_spec(SPEC), root=root)
    return root


def _all_store_text(root: Path) -> str:
    paths = ProjectPaths(root)
    files = [paths.mappings_yaml, *paths.views_dir.glob("*.yaml")]
    for d in (paths.attributes_dir, paths.parameters_dir, paths.roles_dir):
        files.extend(d.glob("*.yaml"))
    return "\n".join(f.read_text(encoding="utf-8") for f in files if f.exists())


def _kinds(root: Path) -> set[str]:
    return {p.kind for p in check_integrity(root=root).problems}


# ── removal cascades ──────────────────────────────────────────────────


def test_built_project_is_clean(project: Path) -> None:
    assert check_integrity(root=project).problems == []


def test_remove_node_takes_its_rows_with_it(project: Path) -> None:
    burnout = get_node("Burnout", root=project)
    edge_ids = [e.id for e in list_edges(root=project) if burnout.id in (e.from_id, e.to_id)]
    open_challenge(burnout.id, "Is burnout the mechanism?", root=project)
    assert burnout.id in _all_store_text(project)

    remove_node("Burnout", root=project)

    text = _all_store_text(project)
    for gone in [burnout.id, *edge_ids]:
        assert gone not in text
    report = check_integrity(root=project)
    assert report.ok
    # The challenge is history: kept, and noted.
    assert [p.kind for p in report.problems] == ["audit_target_removed"]
    assert burnout.id in ProjectPaths(project).challenges_yaml.read_text(encoding="utf-8")


def test_remove_edge_takes_its_rows_with_it(project: Path) -> None:
    edge = next(e for e in list_edges(root=project) if e.from_id == get_node("Workload", root=project).id)
    assert edge.id in _all_store_text(project)
    remove_edge(edge.id, root=project)
    assert edge.id not in _all_store_text(project)
    assert check_integrity(root=project).ok


# ── duplicates refused ────────────────────────────────────────────────


def test_duplicate_label_refused_case_and_space_insensitive(project: Path) -> None:
    with pytest.raises(ValueError, match="already called"):
        add_node("burnout ", root=project)
    add_node("Morale", root=project)
    with pytest.raises(ValueError, match="already called"):
        rename_node("Morale", "WORKLOAD", root=project)
    rename_node("Morale", "morale", root=project)  # changing only its own case is fine


def test_duplicate_edge_refused_but_other_kind_allowed(project: Path) -> None:
    with pytest.raises(DuplicateEdgeError, match="already exists"):
        add_edge("Workload", "Burnout", root=project)
    add_edge("Workload", "Burnout", kind="temporal", root=project)


def test_build_spec_with_a_repeated_link_changes_nothing(project: Path) -> None:
    spec = build_ops.load_spec("links:\n  - {from: Workload, to: Burnout, polarity: '+'}\n")
    with pytest.raises(ValueError, match="already a link"):
        build_ops.build_from_spec(spec, root=project)


# ── check_integrity finds hand-edit damage ────────────────────────────


def test_hand_edited_dangling_endpoint_and_target(project: Path) -> None:
    paths = ProjectPaths(project)
    data = load_raw(paths.conceptual_yaml)
    burnout = next(e for e in data["entities"] if e["label"] == "Burnout")
    data["entities"].remove(burnout)  # removed by hand: edges and rows left pointing at it
    dump_raw(data, paths.conceptual_yaml)

    report = check_integrity(root=project)
    assert not report.ok
    assert {"dangling_edge_endpoint", "dangling_target"} <= _kinds(project)
    assert handover_check(root=project).items[-1].kind == "integrity"


def test_unknown_bibkey_and_duplicates_by_hand(project: Path) -> None:
    paths = ProjectPaths(project)
    ev = load_raw(paths.evidence_links_yaml)
    ev["entries"][0]["bibkey"] = "nosuch2020"
    dump_raw(ev, paths.evidence_links_yaml)
    sub = load_raw(paths.conceptual_yaml)
    sub["edges"].append(dict(sub["edges"][0], id="edge_01J0000000000000000000000Z"))
    sub["entities"].append(dict(sub["entities"][0], id="node_01J0000000000000000000000Z"))
    dump_raw(sub, paths.conceptual_yaml)

    assert {"unknown_bibkey", "duplicate_edge", "duplicate_label"} <= _kinds(project)


def test_malformed_id(project: Path) -> None:
    paths = ProjectPaths(project)
    sub = load_raw(paths.conceptual_yaml)
    sub["entities"].append({"id": "edge_01J0000000000000000000000Z", "kind": "concept", "label": "Odd"})
    sub["entities"].append({"id": "n1", "kind": "concept", "label": "Odder"})
    dump_raw(sub, paths.conceptual_yaml)
    problems = [p for p in check_integrity(root=project).problems if p.kind == "malformed_id"]
    assert len(problems) == 2


def test_source_id_must_match_origin(project: Path) -> None:
    paths = ProjectPaths(project)
    sub = load_raw(paths.conceptual_yaml)
    sub["entities"][0].update(origin="ai-proposed", source_id="interaction_01J0000000000000000000000Z")
    sub["entities"][1].update(origin="human-direct", source_id="interaction_01J0000000000000000000000Z")
    sub["entities"][2].update(origin="imported", source_id="from-another-project")
    dump_raw(sub, paths.conceptual_yaml)

    problems = check_integrity(root=project).problems
    assert {p.kind for p in problems} == {"dangling_source", "source_mismatch"}
    assert all(p.severity == "warning" for p in problems)


def test_fix_removes_leftovers_from_old_removals(project: Path) -> None:
    paths = ProjectPaths(project)
    sub = load_raw(paths.conceptual_yaml)
    burnout = next(e for e in sub["entities"] if e["label"] == "Burnout")
    sub["entities"].remove(burnout)
    sub["edges"] = [e for e in sub["edges"] if burnout["id"] not in (e["from_id"], e["to_id"])]
    dump_raw(sub, paths.conceptual_yaml)
    assert "dangling_target" in _kinds(project)

    removed, sha = remove_dangling_rows(root=project)
    assert removed > 0 and sha
    assert check_integrity(root=project).ok
    assert remove_dangling_rows(root=project) == (0, "")


# ── extract limit ─────────────────────────────────────────────────────


def test_snapshot_extract_limit(project: Path) -> None:
    add_reference("long2020", "Long", root=project)
    with pytest.raises(ValueError, match="limit"):
        set_source_snapshot("long2020", retrieval_url="https://example.org", extract="x" * (SNAPSHOT_EXTRACT_MAX + 1),
                            root=project)
    set_source_snapshot("long2020", retrieval_url="https://example.org", extract="x" * SNAPSHOT_EXTRACT_MAX,
                        root=project)


def test_over_long_extract_on_disk_is_a_warning(project: Path) -> None:
    paths = ProjectPaths(project)
    add_reference("long2020", "Long", root=project)
    set_source_snapshot("long2020", retrieval_url="https://example.org", extract="ok", root=project)
    lib = load_raw(paths.references_yaml)
    for ref in lib["entries"]:
        if ref["bibkey"] == "long2020":
            ref["source_snapshot"]["extract"] = "x" * (SNAPSHOT_EXTRACT_MAX + 5)
    dump_raw(lib, paths.references_yaml)
    report = check_integrity(root=project)
    assert report.ok and {p.kind for p in report.problems} == {"extract_too_long"}


def test_mappings_views_and_data_links_pointing_at_nothing(project: Path) -> None:
    paths = ProjectPaths(project)
    gone = "node_01J0000000000000000000000Z"
    dump_raw({"entries": [{"l2_id": gone}], "left_out": [{"l2_id": "edge_01J0000000000000000000000Z"}]},
             paths.mappings_yaml)
    view = load_raw(paths.view_yaml("cld"))
    view["entity_ids"] = [*(view.get("entity_ids") or []), gone]
    dump_raw(view, paths.view_yaml("cld"))
    dump_raw(["not", "a", "view"], paths.view_yaml("fcm"))  # not a mapping: nothing to check
    dump_raw({"entries": [{"target_id": gone, "dataset_id": "dataset_01J0000000000000000000000Z"}]},
             paths.data_links_yaml)

    problems = check_integrity(root=project).problems
    dangling = {p.where: p.ids for p in problems if p.kind == "dangling_target"}
    assert dangling["substrate/mappings.yaml"] == ["edge_01J0000000000000000000000Z", gone]
    assert dangling["views/cld.yaml"] == [gone]
    assert dangling["substrate/attributes/data-links.yaml"] == [gone]
    assert "views/fcm.yaml" not in dangling
    unknown = next(p for p in problems if p.kind == "unknown_dataset")
    assert unknown.ids == ["dataset_01J0000000000000000000000Z"] and unknown.severity == "error"


def test_files_that_are_not_there_are_not_checked(project: Path) -> None:
    import shutil

    paths = ProjectPaths(project)
    paths.mappings_yaml.unlink()
    paths.challenges_yaml.unlink(missing_ok=True)
    shutil.rmtree(paths.views_dir)
    assert check_integrity(root=project).ok


def test_an_id_used_twice(project: Path) -> None:
    paths = ProjectPaths(project)
    sub = load_raw(paths.conceptual_yaml)
    sub["entities"].append(dict(sub["entities"][0], label="Another"))
    dump_raw(sub, paths.conceptual_yaml)
    problem = next(p for p in check_integrity(root=project).problems if p.kind == "duplicate_id")
    assert problem.ids == [sub["entities"][0]["id"]] and "used 2 times" in problem.message


def test_a_finding_that_supersedes_one_not_recorded(project: Path) -> None:
    import json

    from latris.operations.findings import record_new_finding

    record_new_finding("Workload drives departures.", "dynamics", "cld", root=project)
    path = ProjectPaths(project).findings_jsonl
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    record["supersedes"] = ["finding_01J0000000000000000000000Z"]
    record["target_ids"] = ["node_01J0000000000000000000000Z"]
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    report = check_integrity(root=project)
    problem = next(p for p in report.problems if p.kind == "dangling_supersedes")
    assert problem.severity == "warning" and problem.ids == ["finding_01J0000000000000000000000Z"]
    removed = next(p for p in report.problems if p.kind == "audit_target_removed")
    assert removed.severity == "info" and removed.ids == ["node_01J0000000000000000000000Z"]
    assert report.ok  # neither blocks handover


def test_source_id_naming_the_wrong_kind_of_record(project: Path) -> None:
    from latris.operations.analysis_runs import record_run

    run, _ = record_run(purpose="structure-learning", algorithm="loops", library_version="1", root=project)
    paths = ProjectPaths(project)
    sub = load_raw(paths.conceptual_yaml)
    sub["entities"][0].update(origin="ai-proposed", source_id=run.id)
    sub["entities"][1].update(origin="data-derived", source_id=run.id)  # the right kind: no problem
    dump_raw(sub, paths.conceptual_yaml)
    (problem,) = check_integrity(root=project).problems
    assert problem.kind == "source_mismatch" and problem.ids == [run.id]
    assert problem.message.endswith(f"is ai-proposed but its source_id is an analysis run ({run.id})")
