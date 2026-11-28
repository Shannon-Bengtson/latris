"""Semantic diffs of the substrate and the evidence store (#70).

Unit tests drive ``_diff_substrate`` / ``_diff_evidence`` with built states, so every kind of change is
checked on its own and an unchanged item is shown to produce no entry; the end-to-end tests run the
real operations and diff their commits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.diff.semantic import _diff_evidence, _diff_substrate, diff_commits
from latris.operations import edges as edge_ops
from latris.operations import evidence as evidence_ops
from latris.operations import nodes as node_ops
from latris.operations import references as ref_ops
from latris.repo import git
from latris.schema import EvidenceLink, EvidenceLinkSet, HumanActor, Informants, Substrate
from latris.schema.substrate import Edge, Entity

P = "substrate/conceptual.yaml"


def _ent(i: str, label: str, **kw) -> Entity:
    return Entity(id=f"node_{i}", kind=kw.pop("kind", "variable"), label=label, **kw)


def _edge(i: str, a: str, b: str, **kw) -> Edge:
    return Edge(id=f"edge_{i}", from_id=f"node_{a}", to_id=f"node_{b}", **kw)


def _base() -> Substrate:
    return Substrate(
        entities=[_ent("a", "Rain"), _ent("b", "Flow"), _ent("c", "Flood")],
        edges=[_edge("ab", "a", "b"), _edge("bc", "b", "c")],
    )


def _kinds(events) -> list[str]:
    return [e.kind for e in events]


# ── substrate ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("pair", [(None, None), ("same", "same")])
def test_substrate_unchanged_is_empty(pair) -> None:
    sub = _base() if pair[0] else None
    assert _diff_substrate(sub, _base() if pair[1] else None, P) == []


def test_substrate_from_nothing_adds_everything() -> None:
    events = _diff_substrate(None, _base(), P)
    assert _kinds(events) == ["node_added"] * 3 + ["edge_added"] * 2
    assert events[0].summary == 'Added node "Rain" (variable)'
    assert events[0].target_id == "node_a" and events[0].change == "added" and events[0].path == P
    assert events[3].summary == 'Added edge "Rain" → "Flow" (causal)'


def test_substrate_to_nothing_removes_everything() -> None:
    events = _diff_substrate(_base(), None, P)
    assert _kinds(events) == ["node_removed"] * 3 + ["edge_removed"] * 2
    assert all(e.change == "removed" for e in events)
    # Edge endpoints are named from the old state when the nodes are gone too.
    assert events[3].summary == 'Removed edge "Rain" → "Flow"'


def test_substrate_one_node_and_edge_added_and_removed() -> None:
    old = _base()
    new = _base()
    new.entities = [e for e in new.entities if e.id != "node_c"] + [_ent("d", "Drought", kind="event")]
    new.edges = [_edge("ab", "a", "b"), _edge("ad", "a", "d", kind="temporal")]
    events = _diff_substrate(old, new, P)
    by_kind = {e.kind: e for e in events}
    assert sorted(_kinds(events)) == ["edge_added", "edge_removed", "node_added", "node_removed"]
    assert by_kind["node_added"].summary == 'Added node "Drought" (event)'
    assert by_kind["node_removed"].summary == 'Removed node "Flood"'
    assert by_kind["edge_added"].summary == 'Added edge "Rain" → "Drought" (temporal)'
    assert by_kind["edge_removed"].summary == 'Removed edge "Flow" → "Flood"'
    assert by_kind["edge_removed"].target_id == "edge_bc"


@pytest.mark.parametrize(
    ("field", "value", "kind", "summary"),
    [
        ("label", "Rainfall", "node_renamed", 'Renamed "Rain" → "Rainfall"'),
        ("kind", "event", "node_retyped", 'Retyped node "Rain": variable → event'),
        ("maturity", "approved", "node_maturity_changed", 'Node "Rain" maturity: proposed → approved'),
        ("origin", "ai-proposed", "node_origin_changed", 'Node "Rain" origin: human-direct → ai-proposed'),
        (
            "verification", "human-verified", "node_verification_changed",
            'Node "Rain" verification: unverified → human-verified',
        ),
    ],
)
def test_substrate_node_field_changes(field, value, kind, summary) -> None:
    new = _base()
    setattr(new.entities[0], field, value)
    events = _diff_substrate(_base(), new, P)
    assert [(e.kind, e.summary, e.target_id, e.change) for e in events] == [(kind, summary, "node_a", "changed")]


@pytest.mark.parametrize(
    ("field", "value", "kind", "summary"),
    [
        ("kind", "temporal", "edge_kind_changed", 'Changed edge kind "Rain" → "Flow": causal → temporal'),
        ("maturity", "reviewed", "edge_maturity_changed", 'Edge "Rain" → "Flow" maturity: proposed → reviewed'),
        ("origin", "ai-proposed", "edge_origin_changed", 'Edge "Rain" → "Flow" origin: human-direct → ai-proposed'),
        (
            "verification", "ai-verified", "edge_verification_changed",
            'Edge "Rain" → "Flow" verification: unverified → ai-verified',
        ),
    ],
)
def test_substrate_edge_field_changes(field, value, kind, summary) -> None:
    new = _base()
    setattr(new.edges[0], field, value)
    events = _diff_substrate(_base(), new, P)
    assert [(e.kind, e.summary, e.target_id, e.change) for e in events] == [(kind, summary, "edge_ab", "changed")]


def test_substrate_several_changes_on_one_node() -> None:
    new = _base()
    new.entities[0].label = "Rainfall"
    new.entities[0].maturity = "reviewed"
    events = _diff_substrate(_base(), new, P)
    assert _kinds(events) == ["node_renamed", "node_maturity_changed"]
    assert events[1].summary == 'Node "Rainfall" maturity: proposed → reviewed'


def test_substrate_renamed_endpoint_names_edge_by_new_label() -> None:
    new = _base()
    new.entities[0].label = "Rainfall"
    new.edges[0].kind = "temporal"
    events = _diff_substrate(_base(), new, P)
    assert 'Changed edge kind "Rainfall" → "Flow"' in events[-1].summary


def test_substrate_edge_to_unknown_node_uses_short_id() -> None:
    new = _base()
    new.edges.append(Edge(id="edge_zz", from_id="node_a", to_id="node_01HZZZZZZZZZZZZZZZZZZZZZZZ"))
    (event,) = _diff_substrate(_base(), new, P)
    assert event.summary == 'Added edge "Rain" → "node_01HZZZZZZZ…" (causal)'


def test_substrate_reordering_is_not_a_change() -> None:
    new = _base()
    new.entities.reverse()
    new.edges.reverse()
    assert _diff_substrate(_base(), new, P) == []


# ── evidence ────────────────────────────────────────────────────────────

E = "evidence/links.yaml"


def _link(bibkey: str = "smith2023", target: str | None = "node_a", **kw) -> EvidenceLink:
    return EvidenceLink(target_id=target, attribute=kw.pop("attribute", "description"), bibkey=bibkey, **kw)


def _set(*links: EvidenceLink) -> EvidenceLinkSet:
    return EvidenceLinkSet(entries=list(links))


@pytest.mark.parametrize("pair", [(None, None), ("same", "same")])
def test_evidence_unchanged_is_empty(pair) -> None:
    def build():
        return _set(_link(), _link("jones2020"), _link("doe2019", target=None)) if pair[0] else None

    assert _diff_evidence(build(), build(), E) == []


def test_evidence_attached_and_detached() -> None:
    old = _set(_link("smith2023"), _link("jones2020"))
    new = _set(_link("smith2023"), _link("doe2019", attribute="polarity"))
    events = _diff_evidence(old, new, E)
    assert [(e.kind, e.summary, e.target_id) for e in events] == [
        ("evidence_attached", 'Attached "doe2019" to node_a/polarity', "node_a"),
        ("evidence_detached", 'Detached "jones2020" from node_a/description', "node_a"),
    ]
    assert all(e.change == "changed" for e in events)  # a citation changes the claim it's on


def test_evidence_same_source_on_another_claim_is_a_new_citation() -> None:
    old = _set(_link())
    new = _set(_link(), _link(target="node_b"))
    (event,) = _diff_evidence(old, new, E)
    assert event.kind == "evidence_attached" and event.target_id == "node_b"


def test_evidence_on_the_model_as_a_whole() -> None:
    """Evidence with no target (it supports the model) used to crash the diff."""
    events = _diff_evidence(None, _set(_link(target=None)), E)
    assert [(e.kind, e.summary, e.target_id) for e in events] == [
        ("evidence_attached", 'Attached "smith2023" to model/description', None),
    ]
    assert _diff_evidence(_set(_link(target=None)), None, E)[0].summary == (
        'Detached "smith2023" from model/description'
    )
    (changed,) = _diff_evidence(_set(_link(target=None)), _set(_link(target=None, support_verdict="supports")), E)
    assert changed.summary == 'Evidence "smith2023" on model/description: support_verdict: unverified → supports'


@pytest.mark.parametrize(
    ("changes", "part"),
    [
        ({"origin": "ai-proposed"}, "origin: human-direct → ai-proposed"),
        ({"verified_by": "ai"}, "verified_by: human → ai"),
        ({"source_access": "abstract"}, "source_access: title_only → abstract"),
        ({"support_verdict": "contradicts"}, "support_verdict: unverified → contradicts"),
        ({"stance": "against"}, "stance: for → against"),
        ({"quote": "A passage copied from the source."}, "quote updated"),
        ({"quote_verified": False}, "quote_verified: None → False"),
        ({"informants": Informants(approved_by=[HumanActor(name="R")])}, "informants updated"),
    ],
)
def test_evidence_field_changes(changes, part) -> None:
    (event,) = _diff_evidence(_set(_link(), _link("jones2020")), _set(_link(**changes), _link("jones2020")), E)
    assert event.kind == "evidence_changed"
    assert event.summary == f'Evidence "smith2023" on node_a/description: {part}'
    assert event.target_id == "node_a" and event.change == "changed"


def test_evidence_quote_removed() -> None:
    old = _set(_link(quote="A passage copied from the source.", quote_verified=True))
    (event,) = _diff_evidence(old, _set(_link()), E)
    assert event.summary.endswith("quote removed; quote_verified: True → None")


def test_evidence_check_reports_every_axis_that_moved() -> None:
    new = _link(support_verdict="supports", source_access="abstract", quote="Passage.", quote_verified=True)
    (event,) = _diff_evidence(_set(_link()), _set(new), E)
    assert event.summary == (
        'Evidence "smith2023" on node_a/description: source_access: title_only → abstract; '
        "support_verdict: unverified → supports; quote updated; quote_verified: None → True"
    )


def test_evidence_notes_only_change_is_not_reported() -> None:
    assert _diff_evidence(_set(_link()), _set(_link(notes="reread")), E) == []


# ── end to end, through the operations ──────────────────────────────────


def _diff_last(root: Path):
    head = git.run_git(["rev-parse", "HEAD"], cwd=root).stdout.strip()
    return diff_commits(root, f"{head}^", head)


def test_diff_model_level_evidence_attached(two_node_project_root: Path) -> None:
    root = two_node_project_root
    ref_ops.add_reference("smith2023", title="X", root=root)
    evidence_ops.add_evidence(None, "framing", "smith2023", root=root)
    events = [e for e in _diff_last(root) if e.kind.startswith("evidence")]
    assert [(e.kind, e.summary) for e in events] == [("evidence_attached", 'Attached "smith2023" to model/framing')]


def test_diff_evidence_detached_and_checked(two_node_project_root: Path) -> None:
    root = two_node_project_root
    price = node_ops.list_nodes(root=root)[0]
    ref_ops.add_reference("smith2023", title="X", root=root)
    evidence_ops.add_evidence(price.id, "description", "smith2023", root=root)

    evidence_ops.set_evidence_support_verdict(
        price.id, "description", "smith2023", new_verdict="contradicts", rationale="read it", root=root
    )
    (checked,) = [e for e in _diff_last(root) if e.kind.startswith("evidence")]
    assert checked.kind == "evidence_changed"
    assert checked.summary == 'Evidence "smith2023" on Price/description: support_verdict: unverified → contradicts'

    # The same verdict with a new quote is a new check: the diff shows the quote moved.
    evidence_ops.set_evidence_support_verdict(
        price.id, "description", "smith2023", new_verdict="contradicts", rationale="again",
        quote="A passage that Latris does not hold.", checked_by="human", root=root,
    )
    (requoted,) = [e for e in _diff_last(root) if e.kind.startswith("evidence")]
    assert requoted.summary.endswith("quote updated; quote_verified: None → False")

    evidence_ops.remove_evidence(price.id, "description", "smith2023", root=root)
    (detached,) = [e for e in _diff_last(root) if e.kind.startswith("evidence")]
    assert detached.summary == 'Detached "smith2023" from Price/description'


def test_diff_edge_change_names_endpoints(two_node_project_root: Path) -> None:
    root = two_node_project_root
    edge = edge_ops.list_edges(root=root)[0]
    from latris.operations import maturity as maturity_ops

    maturity_ops.mark_reviewed(edge.id, root=root)
    (event,) = _diff_last(root)
    assert (event.kind, event.summary) == ("edge_maturity_changed", 'Edge "Price" → "Demand" maturity: proposed → reviewed')


# ── the other stores, and the engine ────────────────────────────────────


def test_challenge_on_the_model_as_a_whole(empty_project_root: Path) -> None:
    """A project-level challenge (no target) used to crash the diff, like model-level evidence."""
    from latris.operations import challenges as ch_ops

    ch_ops.open_challenge(None, "The boundary is too narrow", root=empty_project_root)
    (event,) = _diff_last(empty_project_root)
    assert (event.kind, event.summary) == ("challenge_opened", "Opened challenge on model: The boundary is too narrow")


def test_challenge_reopened_turns_added_and_removed() -> None:
    from latris.diff.semantic import _diff_challenges
    from latris.schema import ChallengeLog
    from latris.schema.ai import Challenge, ConversationTurn

    me = HumanActor(name="R")
    old = Challenge(id="challenge_1", target_id="node_a", target_attribute="polarity", argument="x",
                    opened_by=me, state="modified")
    new = old.model_copy(update={"state": "open", "conversation": [ConversationTurn(speaker=me, message="m")]})
    events = _diff_challenges(ChallengeLog(entries=[old]), ChallengeLog(entries=[new]), "p")
    assert _kinds(events) == ["challenge_reopened", "challenge_turns_added"]
    assert events[1].summary == "Added 1 turn(s) to challenge challenge_1"
    # Fewer turns (or an edit to the argument only) is not reported.
    assert _diff_challenges(ChallengeLog(entries=[new]), ChallengeLog(entries=[new.model_copy(update={
        "conversation": []})]), "p") == []
    (opened,) = _diff_challenges(None, ChallengeLog(entries=[old]), "p")
    assert opened.summary == "Opened challenge on node_a/polarity: x"
    (removed,) = _diff_challenges(ChallengeLog(entries=[old]), None, "p")
    assert (removed.kind, removed.change) == ("challenge_removed", "removed")


def test_attribute_changes_and_removal() -> None:
    from latris.diff.semantic import _diff_attribute_set
    from latris.schema import DescriptionSet
    from latris.schema.attributes import DescriptionEntry

    old = DescriptionEntry(target_id="node_a", value="Rain")
    new = old.model_copy(update={
        "contested": True, "origin": "ai-proposed", "verification": "human-verified",
        "informants": Informants(proposed_by=[HumanActor(name="R")]),
    })
    (event,) = _diff_attribute_set(DescriptionSet(entries=[old]), DescriptionSet(entries=[new]), "p")
    assert event.summary == (
        "description on node_a: contested: False → True; informants updated; origin: human-direct → ai-proposed; "
        "verification: unverified → human-verified"
    )
    (removed,) = _diff_attribute_set(DescriptionSet(entries=[old]), None, "p")
    assert (removed.kind, removed.summary) == ("attribute_removed", "Removed description from node_a")
    assert _diff_attribute_set(DescriptionSet(entries=[old]), DescriptionSet(entries=[old]), "p") == []


def test_mappings_and_left_out(two_node_project_root: Path) -> None:
    from latris.operations import mappings as mapping_ops

    root = two_node_project_root
    price = node_ops.list_nodes(root=root)[0]
    mapping_ops.map_to_view(price.id, "fcm", root=root)
    (added,) = _diff_last(root)
    assert (added.kind, added.summary, added.change) == ("mapping_added", "Put Price in the fcm view", "changed")

    mapping_ops.leave_out(price.id, "fcm", reason="not a concept here", root=root)
    events = {e.kind: e.summary for e in _diff_last(root)}
    assert events == {
        "mapping_removed": "Took Price out of the fcm view",
        "left_out_of_view": "Left Price out of the fcm view: not a concept here",
    }

    mapping_ops.map_to_view(price.id, "fcm", root=root)
    events = {e.kind: e.summary for e in _diff_last(root)}
    assert events["put_back_in_view"] == "Put Price back in the fcm view"


def test_log_entry_and_reference_removed() -> None:
    from latris.diff.semantic import _diff_references, _make_log_differ
    from latris.schema import AssumptionLog, ReferenceLibrary
    from latris.schema.provenance import Assumption
    from latris.schema.references import Reference

    a = Assumption(id="assumption_01HABCDEFGHJKMNPQRS", statement="s", authored_by=HumanActor(name="R"))
    (gone,) = _make_log_differ("assumption")(AssumptionLog(entries=[a]), None, "p")
    assert (gone.kind, gone.summary) == ("assumption_removed", "Removed assumption assumption_01HA…")
    (ref,) = _diff_references(ReferenceLibrary(entries=[Reference(bibkey="k", title="T")]), None, "p")
    assert (ref.kind, ref.summary) == ("reference_removed", 'Removed reference "k"')


def test_project_diff_edges() -> None:
    from latris.diff.semantic import _diff_project
    from latris.schema import ProjectFoundation

    f = ProjectFoundation(statement="Q?")
    assert _diff_project(f, None, "p") == []
    assert _diff_project(f, f, "p") == []


def test_unregistered_model_file_is_reported_as_a_file_change(empty_project_root: Path) -> None:
    root = empty_project_root
    (root / "notes.txt").write_text("hello\n", encoding="utf-8")
    from latris.diff.semantic import diff_working_tree

    assert [(e.kind, e.summary) for e in diff_working_tree(root)] == [("file_changed", "?? notes.txt")]
    git.run_git(["add", "notes.txt"], cwd=root)
    git.run_git(["commit", "-qm", "notes"], cwd=root)
    assert [(e.kind, e.summary) for e in _diff_last(root)] == [("file_changed", "A notes.txt")]


def test_name_status_parsing_keeps_rename_destination() -> None:
    from latris.diff.semantic import _parse_name_status_z

    stream = "M\x00a.yaml\x00R100\x00old.yaml\x00new.yaml\x00D\x00gone.yaml\x00"
    assert _parse_name_status_z(stream) == [("M", "a.yaml"), ("R", "new.yaml"), ("D", "gone.yaml")]
