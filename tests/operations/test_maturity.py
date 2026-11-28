"""Maturity operations: propose / mark_reviewed / approve across every artifact store (#70).

Each round trip sets maturity through the public operation, reloads the store from disk and checks that
only that item's ``maturity`` changed, that the commit touched only the store it should, and that a target
nothing matches (or whose store doesn't exist yet) is refused without writing anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import lineage as lineage_ops
from latris.operations import mappings as mapping_ops
from latris.operations import maturity as maturity_ops
from latris.operations.findings import record_new_finding
from latris.repo import git
from latris.repo.project import require_project
from latris.repo.yaml_io import iter_jsonl, load_model
from latris.schema import (
    Finding,
    HumanActor,
    LineageNode,
    MappingRegistry,
    MilestoneLog,
    SignoffLog,
    Substrate,
)

SETTERS = [
    (maturity_ops.propose, "proposed"),
    (maturity_ops.mark_reviewed, "reviewed"),
    (maturity_ops.approve, "approved"),
]


def _head(root: Path) -> str:
    return git.run_git(["rev-parse", "HEAD"], cwd=root).stdout.strip()


def _files_in_head(root: Path) -> set[str]:
    out = git.run_git(["show", "--name-only", "--format=", "HEAD"], cwd=root).stdout
    return {line for line in out.splitlines() if line}


def _clean(root: Path) -> bool:
    return git.run_git(["status", "--porcelain"], cwd=root).stdout.strip() == ""


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _dumps(items, changed_id: str, key: str = "id") -> tuple[dict, list[dict]]:
    """The changed item without its maturity, and every other item in full."""
    target = next(i for i in items if getattr(i, key) == changed_id)
    return (
        target.model_dump(mode="json", exclude={"maturity"}),
        [i.model_dump(mode="json") for i in items if getattr(i, key) != changed_id],
    )


def _assert_refused(root: Path, target: str) -> None:
    head = _head(root)
    for fn, _ in SETTERS:
        with pytest.raises(ValueError, match="no entity, edge, mapping, finding, milestone, or lineage node"):
            fn(target, root=root)
    assert _head(root) == head
    assert _clean(root)


# ── Substrate: entities and edges ───────────────────────────────────────


@pytest.mark.parametrize(("setter", "level"), SETTERS)
def test_entity_round_trip(two_node_project_root: Path, setter, level) -> None:
    root = two_node_project_root
    paths = require_project(root)
    before = load_model(Substrate, paths.conceptual_yaml)
    price = next(e for e in before.entities if e.label == "Price")
    if level == "proposed":  # start somewhere else so the change is visible
        maturity_ops.mark_reviewed(price.id, root=root)
        before = load_model(Substrate, paths.conceptual_yaml)
    head = _head(root)

    result, sha = setter("price", root=root)  # by label, case-insensitive

    assert result == level
    assert sha == _head(root) != head
    after = load_model(Substrate, paths.conceptual_yaml)
    assert next(e for e in after.entities if e.id == price.id).maturity == level
    assert _dumps(after.entities, price.id) == _dumps(before.entities, price.id)
    assert [e.model_dump() for e in after.edges] == [e.model_dump() for e in before.edges]
    expected = {_rel(root, paths.conceptual_yaml)}
    if level == "approved":
        expected.add(_rel(root, paths.signoffs_yaml))
    assert _files_in_head(root) == expected
    assert _clean(root)


def test_edge_round_trip_by_id_and_by_name(two_node_project_root: Path) -> None:
    root = two_node_project_root
    paths = require_project(root)
    before = load_model(Substrate, paths.conceptual_yaml)
    edge = before.edges[0]

    maturity_ops.mark_reviewed(edge.id, root=root)
    mid = load_model(Substrate, paths.conceptual_yaml)
    assert mid.edges[0].maturity == "reviewed"
    assert mid.edges[0].model_dump(exclude={"maturity"}) == edge.model_dump(exclude={"maturity"})
    assert [e.model_dump() for e in mid.entities] == [e.model_dump() for e in before.entities]

    maturity_ops.propose("Price -> Demand", root=root)
    assert load_model(Substrate, paths.conceptual_yaml).edges[0].maturity == "proposed"


def test_edge_by_id_prefix(two_node_project_root: Path) -> None:
    root = two_node_project_root
    paths = require_project(root)
    edge = load_model(Substrate, paths.conceptual_yaml).edges[0]
    level, _ = maturity_ops.mark_reviewed(edge.id[:12], root=root)
    assert level == "reviewed"
    assert load_model(Substrate, paths.conceptual_yaml).edges[0].maturity == "reviewed"


def test_approve_writes_signoff(two_node_project_root: Path, git_identity) -> None:
    root = two_node_project_root
    paths = require_project(root)
    price = next(e for e in load_model(Substrate, paths.conceptual_yaml).entities if e.label == "Price")
    before = load_model(SignoffLog, paths.signoffs_yaml).entries

    maturity_ops.approve(price.id, root=root)
    reviewer = HumanActor(name="R. Viewer", email="r@example.org")
    maturity_ops.approve(price.id, reviewer=reviewer, role="Lead", scope="Factor", notes="ok", root=root)

    entries = load_model(SignoffLog, paths.signoffs_yaml).entries
    assert entries[: len(before)] == before
    first, second = entries[len(before):]
    assert first.target_id == price.id and first.reviewer.name == git_identity[0]
    assert (first.role, first.scope, first.notes) == ("Reviewer", "Model", None)
    assert second.reviewer == reviewer
    assert (second.role, second.scope, second.notes) == ("Lead", "Factor", "ok")
    assert first.id != second.id


def test_unknown_target_is_refused(two_node_project_root: Path) -> None:
    _assert_refused(two_node_project_root, "no_such_thing_anywhere")


# ── Mappings ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("setter", "level"), SETTERS)
def test_mapping_round_trip(two_node_project_root: Path, setter, level) -> None:
    root = two_node_project_root
    paths = require_project(root)
    sub = load_model(Substrate, paths.conceptual_yaml)
    price, demand = sub.entities
    mapping_ops.map_to_view(price.id, "fcm", l3_id="fcmnode.price", ai_proposed=level != "proposed", root=root)
    mapping_ops.map_to_view(demand.id, "fcm", l3_id="fcmnode.demand", root=root)
    before = load_model(MappingRegistry, paths.mappings_yaml)
    sub_before = load_model(Substrate, paths.conceptual_yaml)

    result, _ = setter("fcmnode.price", root=root)

    assert result == level
    after = load_model(MappingRegistry, paths.mappings_yaml)
    target = next(m for m in after.entries if m.l3_id == "fcmnode.price")
    assert target.maturity == level
    assert _dumps(after.entries, "fcmnode.price", key="l3_id") == _dumps(before.entries, "fcmnode.price", key="l3_id")
    assert after.left_out == before.left_out
    assert load_model(Substrate, paths.conceptual_yaml) == sub_before
    expected = {_rel(root, paths.mappings_yaml)}
    if level == "approved":
        expected.add(_rel(root, paths.signoffs_yaml))
    assert _files_in_head(root) == expected


def test_mapping_store_missing(two_node_project_root: Path) -> None:
    root = two_node_project_root
    paths = require_project(root)
    paths.mappings_yaml.unlink()
    git.run_git(["commit", "-qam", "drop mappings"], cwd=root)
    _assert_refused(root, "fcmnode.price")
    assert not paths.mappings_yaml.exists()


# ── Findings ─────────────────────────────────────────────────────────────


def _two_findings(root: Path) -> tuple[Finding, Finding]:
    a, _ = record_new_finding("First", "structure", "cld", detail="d1", payload={"n": 1}, root=root)
    b, _ = record_new_finding("Second", "dynamics", "cld", target_ids=["node_x"], root=root)
    return a, b


@pytest.mark.parametrize(("setter", "level"), SETTERS)
def test_finding_round_trip(two_node_project_root: Path, setter, level) -> None:
    root = two_node_project_root
    paths = require_project(root)
    first, second = _two_findings(root)
    if level == "proposed":
        maturity_ops.mark_reviewed(second.id, root=root)
    before = list(iter_jsonl(Finding, paths.findings_jsonl))
    sub_before = load_model(Substrate, paths.conceptual_yaml)

    result, _ = setter(second.id, root=root)

    assert result == level
    after = list(iter_jsonl(Finding, paths.findings_jsonl))
    assert [f.id for f in after] == [first.id, second.id]  # order kept, nothing duplicated
    assert next(f for f in after if f.id == second.id).maturity == level
    assert _dumps(after, second.id) == _dumps(before, second.id)
    assert load_model(Substrate, paths.conceptual_yaml) == sub_before
    expected = {_rel(root, paths.findings_jsonl)}
    if level == "approved":
        expected.add(_rel(root, paths.signoffs_yaml))
        assert load_model(SignoffLog, paths.signoffs_yaml).entries[-1].target_id == second.id
    assert _files_in_head(root) == expected


def test_findings_store_missing(empty_project_root: Path) -> None:
    root = empty_project_root
    assert not require_project(root).findings_jsonl.exists()
    _assert_refused(root, "finding_01ABCDEFGHJKMNPQRSTVWXYZ00")
    assert not require_project(root).findings_jsonl.exists()


def test_unknown_finding_id_leaves_findings_untouched(two_node_project_root: Path) -> None:
    root = two_node_project_root
    paths = require_project(root)
    _two_findings(root)
    text = paths.findings_jsonl.read_text(encoding="utf-8")
    _assert_refused(root, "finding_01ABCDEFGHJKMNPQRSTVWXYZ00")
    assert paths.findings_jsonl.read_text(encoding="utf-8") == text


# ── Milestones ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(("setter", "level"), SETTERS)
def test_milestone_round_trip(two_node_project_root: Path, setter, level) -> None:
    root = two_node_project_root
    paths = require_project(root)
    start = "reviewed" if level == "proposed" else "proposed"
    m1, _ = lineage_ops.create_milestone("First draft", maturity=start, notes="n1", root=root)
    m2, _ = lineage_ops.create_milestone("Second draft", maturity=start, root=root)
    before = load_model(MilestoneLog, paths.milestones_yaml).entries
    node_before = load_model(LineageNode, paths.lineage_node_yaml)

    result, _ = setter(m1.id, root=root)

    assert result == level
    after = load_model(MilestoneLog, paths.milestones_yaml).entries
    assert [m.id for m in after] == [m1.id, m2.id]
    assert after[0].maturity == level
    assert _dumps(after, m1.id) == _dumps(before, m1.id)
    assert load_model(LineageNode, paths.lineage_node_yaml) == node_before
    expected = {_rel(root, paths.milestones_yaml)}
    if level == "approved":
        expected.add(_rel(root, paths.signoffs_yaml))
    assert _files_in_head(root) == expected


def test_milestone_store_missing(two_node_project_root: Path) -> None:
    root = two_node_project_root
    paths = require_project(root)
    assert not paths.milestones_yaml.exists()
    _assert_refused(root, "milestone_01ABCDEFGHJKMNPQRSTVWXYZ00")
    assert not paths.milestones_yaml.exists()


def test_unknown_milestone_id(two_node_project_root: Path) -> None:
    root = two_node_project_root
    paths = require_project(root)
    lineage_ops.create_milestone("Draft", root=root)
    text = paths.milestones_yaml.read_text(encoding="utf-8")
    _assert_refused(root, "milestone_01ABCDEFGHJKMNPQRSTVWXYZ00")
    assert paths.milestones_yaml.read_text(encoding="utf-8") == text


# ── Lineage node ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(("setter", "level"), SETTERS)
def test_lineage_round_trip(two_node_project_root: Path, setter, level) -> None:
    root = two_node_project_root
    paths = require_project(root)
    node = lineage_ops.ensure_root_lineage(root)
    if level == "proposed":
        maturity_ops.mark_reviewed(node.id, root=root)
    before = load_model(LineageNode, paths.lineage_node_yaml)
    milestones_before = paths.milestones_yaml.read_text(encoding="utf-8")

    result, _ = setter(node.id, root=root)

    assert result == level
    after = load_model(LineageNode, paths.lineage_node_yaml)
    assert after.maturity == level
    assert after.model_dump(exclude={"maturity"}) == before.model_dump(exclude={"maturity"})
    assert paths.milestones_yaml.read_text(encoding="utf-8") == milestones_before
    expected = {_rel(root, paths.lineage_node_yaml)}
    if level == "approved":
        expected.add(_rel(root, paths.signoffs_yaml))
    assert _files_in_head(root) == expected


def test_lineage_store_missing(two_node_project_root: Path) -> None:
    root = two_node_project_root
    assert not require_project(root).lineage_node_yaml.exists()
    _assert_refused(root, "version_01ABCDEFGHJKMNPQRSTVWXYZ00")
    assert not require_project(root).lineage_node_yaml.exists()


def test_other_lineage_id_is_refused(two_node_project_root: Path) -> None:
    root = two_node_project_root
    paths = require_project(root)
    lineage_ops.ensure_root_lineage(root)
    text = paths.lineage_node_yaml.read_text(encoding="utf-8")
    _assert_refused(root, "version_01ABCDEFGHJKMNPQRSTVWXYZ00")
    assert paths.lineage_node_yaml.read_text(encoding="utf-8") == text


# ── Invalid maturity ─────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["bogus", "Approved", "", None])
def test_invalid_maturity_is_refused_before_writing(two_node_project_root: Path, bad) -> None:
    """The setters assign without validation, so the chokepoint checks the level before anything is written."""
    root = two_node_project_root
    paths = require_project(root)
    price = load_model(Substrate, paths.conceptual_yaml).entities[0]
    text = paths.conceptual_yaml.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="maturity"):
        maturity_ops._resolve_and_set(price.id, bad, paths)
    assert paths.conceptual_yaml.read_text(encoding="utf-8") == text
    assert load_model(Substrate, paths.conceptual_yaml).entities[0].maturity == price.maturity


# ── Derived badges ───────────────────────────────────────────────────────


def test_badges_all_false_on_a_bare_factor(two_node_project_root: Path) -> None:
    root = two_node_project_root
    price = load_model(Substrate, require_project(root).conceptual_yaml).entities[0]
    badges = maturity_ops.compute_badges(price.id, model_type="fcm", root=root)
    assert badges.model_dump() == {
        "has_evidence": False,
        "has_challenges": False,
        "has_formalism": False,
        "has_quantification": False,
        "has_confirmed_prediction": False,
    }


def test_badges_evidence_and_open_challenges_are_per_target(two_node_project_root: Path) -> None:
    from latris.operations import challenges as ch_ops
    from latris.operations import evidence as evidence_ops
    from latris.operations import references as ref_ops

    root = two_node_project_root
    price, demand = load_model(Substrate, require_project(root).conceptual_yaml).entities
    ref_ops.add_reference("smith2023", title="X", root=root)
    evidence_ops.add_evidence(price.id, "description", "smith2023", root=root)
    ch, _ = ch_ops.open_challenge(price.id, "arguable", root=root)

    on_price = maturity_ops.compute_badges(price.id, root=root)
    assert on_price.has_evidence and on_price.has_challenges
    on_demand = maturity_ops.compute_badges(demand.id, root=root)
    assert not on_demand.has_evidence and not on_demand.has_challenges

    ch_ops.resolve_challenge(ch.id, "modified", root=root)
    assert not maturity_ops.compute_badges(price.id, root=root).has_challenges  # only open ones count


def test_badges_formalism_follows_model_type(two_node_project_root: Path) -> None:
    root = two_node_project_root
    price, demand = load_model(Substrate, require_project(root).conceptual_yaml).entities
    mapping_ops.map_to_view(price.id, "fcm", root=root)
    assert maturity_ops.compute_badges(price.id, root=root).has_formalism
    assert maturity_ops.compute_badges(price.id, model_type="fcm", root=root).has_formalism
    assert not maturity_ops.compute_badges(price.id, model_type="sd", root=root).has_formalism
    assert not maturity_ops.compute_badges(demand.id, root=root).has_formalism


def test_badges_quantification_skips_unreadable_parameter_files(sd_bathtub_root: Path) -> None:
    from latris.operations.nodes import list_nodes

    root = sd_bathtub_root
    ids = {n.label: n.id for n in list_nodes(root=root)}
    params = require_project(root).parameters_dir
    (params / "sd-aaa-broken.yaml").write_text("entries: not-a-list\n", encoding="utf-8")
    (params / "sd-aab-not-yaml.yaml").write_text("entries: [unclosed\n", encoding="utf-8")
    assert maturity_ops.compute_badges(ids["Drain Rate"], model_type="sd", root=root).has_quantification
    assert not maturity_ops.compute_badges(ids["Tap"], model_type="sd", root=root).has_quantification  # reads every file
    assert not maturity_ops.compute_badges(ids["Drain Rate"], model_type="fcm", root=root).has_quantification
    assert not maturity_ops.compute_badges(ids["Drain Rate"], root=root).has_quantification


def test_badges_confirmed_prediction_is_project_wide(two_node_project_root: Path) -> None:
    from latris.operations import provenance as prov_ops
    from latris.repo.yaml_io import dump_model
    from latris.schema import PredictionLog

    root = two_node_project_root
    paths = require_project(root)
    price = load_model(Substrate, paths.conceptual_yaml).entities[0]
    prov_ops.add_prediction("Demand falls", horizon="6 months", root=root)
    assert not maturity_ops.compute_badges(price.id, root=root).has_confirmed_prediction

    log = load_model(PredictionLog, paths.predictions_yaml)
    log.entries[0].resolution = "confirmed"
    dump_model(log, paths.predictions_yaml)
    assert maturity_ops.compute_badges(price.id, root=root).has_confirmed_prediction
