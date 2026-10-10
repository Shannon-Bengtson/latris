from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations import attributes as attr_ops
from latris.operations import challenges as ch_ops
from latris.operations import edges as edge_ops
from latris.operations import nodes as node_ops
from latris.operations import view_attributes as view_attr_ops
from latris.operations.init import init_project
from latris.repo import git
from latris.repo.yaml_io import load_model
from latris.schema import ChallengeLog, PolaritySet


@pytest.fixture
def project_with_edge(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    a, _ = node_ops.add_node("Price", kind="variable", root=root)
    b, _ = node_ops.add_node("Demand", kind="variable", root=root)
    edge, _ = edge_ops.add_edge(a.id, b.id, root=root)
    return root, a, b, edge


def _commit_count(root: Path) -> int:
    return int(git.run_git(["rev-list", "--count", "HEAD"], cwd=root).stdout.strip())


def test_open_challenge_appends_entry(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    before = _commit_count(root)
    ch, sha = ch_ops.open_challenge(
        edge.id,
        "The edge direction is arguable.",
        root=root,
    )
    assert ch.state == "open"
    assert ch.target_id == edge.id
    assert ch.argument == "The edge direction is arguable."

    log = load_model(ChallengeLog, root / "ai" / "challenges.yaml")
    assert len(log.entries) == 1
    assert log.entries[0].id == ch.id
    assert _commit_count(root) == before + 1
    assert len(sha) == 40


def test_open_with_attribute_records_target_attribute(project_with_edge) -> None:
    """Challenges against a specific attribute record the attribute name.

    Attribute-level maturity was removed when maturity moved to the
    parent Entity/Edge — the ``has_challenges`` derived badge picks
    up the contention signal at fetch time. See
    docs/design/MATURITY_LADDER.md.
    """
    root, _, _, edge = project_with_edge
    view_attr_ops.set_view_attribute(edge.id, "cld", "polarity", "-", root=root)

    ch, _ = ch_ops.open_challenge(edge.id, "Polarity disputed.", attribute="polarity", root=root)
    assert ch.target_attribute == "polarity"
    assert ch.target_id == edge.id
    assert ch.state == "open"

    # The polarity store itself is unchanged — no per-attribute maturity to flip.
    polarity_path = root / "views" / "parameters" / "cld-polarity.yaml"
    after = load_model(PolaritySet, polarity_path)
    assert after.entries[0].value == "-"


def test_open_with_attribute_not_present_is_silent(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    # No polarity set — opening a challenge against it should still succeed.
    ch, _ = ch_ops.open_challenge(
        edge.id,
        "Would be disputed.",
        attribute="polarity",
        root=root,
    )
    assert ch.target_attribute == "polarity"


def test_resolve_to_terminal_state(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=root)

    resolved, _ = ch_ops.resolve_challenge(
        ch.id,
        "retained-with-caveat",
        rationale="Caveat about scope.",
        root=root,
    )
    assert resolved.state == "retained-with-caveat"
    assert resolved.resolved_at is not None
    assert resolved.resolution_rationale == "Caveat about scope."


def test_resolve_refuses_open_state(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=root)
    with pytest.raises(ValueError, match="cannot resolve to 'open'"):
        ch_ops.resolve_challenge(ch.id, "open", root=root)


def test_resolve_rejects_unknown_state(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=root)
    with pytest.raises(ValueError, match="unknown state"):
        ch_ops.resolve_challenge(ch.id, "bogus", root=root)  # type: ignore[arg-type]


def test_resolve_refuses_already_resolved(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=root)
    ch_ops.resolve_challenge(ch.id, "removed", root=root)
    with pytest.raises(ValueError, match="already resolved"):
        ch_ops.resolve_challenge(ch.id, "modified", root=root)


def test_resolve_by_prefix(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=root)
    prefix = ch.id[:30]
    resolved, _ = ch_ops.resolve_challenge(prefix, "modified", root=root)
    assert resolved.id == ch.id


def test_add_turn_appends_conversation(project_with_edge, git_identity) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=root)

    ch_ops.add_turn(ch.id, "Consider simultaneity bias.", root=root)
    ch_ops.add_turn(ch.id, "Fair point, but we control for it via X.", root=root)

    refreshed = ch_ops.get_challenge(ch.id, root=root)
    assert len(refreshed.conversation) == 2
    assert refreshed.conversation[0].message.startswith("Consider")
    assert refreshed.conversation[0].speaker.name == git_identity[0]


def test_add_turn_refuses_closed_challenge(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "arg", root=root)
    ch_ops.resolve_challenge(ch.id, "retained-unchanged", root=root)
    with pytest.raises(ValueError, match="closed"):
        ch_ops.add_turn(ch.id, "Late turn.", root=root)


def test_list_and_get(project_with_edge) -> None:
    root, _, _, edge = project_with_edge
    assert ch_ops.list_challenges(root) == []
    ch1, _ = ch_ops.open_challenge(edge.id, "arg1", root=root)
    ch2, _ = ch_ops.open_challenge(edge.id, "arg2", root=root)
    listed = ch_ops.list_challenges(root)
    assert [c.id for c in listed] == [ch1.id, ch2.id]

    fetched = ch_ops.get_challenge(ch1.id, root=root)
    assert fetched.argument == "arg1"


def test_challenge_on_node(project_with_edge) -> None:
    root, a, _, _ = project_with_edge
    ch, _ = ch_ops.open_challenge("Price", "This node is too narrow.", root=root)
    assert ch.target_id == a.id


# -- All terminal states --


@pytest.mark.parametrize(
    "state",
    [
        "retained-unchanged",
        "retained-with-caveat",
        "modified",
        "split",
        "removed",
        "unresolved",
    ],
)
def test_resolve_all_terminal_states(project_with_edge, state) -> None:
    root, _, _, edge = project_with_edge
    ch, _ = ch_ops.open_challenge(edge.id, "testing each state", root=root)
    resolved, sha = ch_ops.resolve_challenge(ch.id, state, root=root)
    assert resolved.state == state
    assert resolved.resolved_at is not None
    assert len(sha) == 40


# -- Global challenge (no target) --


def test_global_challenge_no_target(project_with_edge) -> None:
    root, _, _, _ = project_with_edge
    ch, sha = ch_ops.open_challenge(None, "The model framing is wrong.", root=root)
    assert ch.target_id is None
    assert ch.state == "open"
    assert len(sha) == 40

    # Can resolve it
    resolved, _ = ch_ops.resolve_challenge(ch.id, "retained-with-caveat", root=root)
    assert resolved.state == "retained-with-caveat"


# -- Attribute-targeted challenges record the attribute name without
# touching the attribute store. The "is challenged?" signal now surfaces
# as a derived MaturityBadges flag computed from the Challenge log.


def test_open_challenge_against_description_records_target_attribute(project_with_edge) -> None:
    root, a, _, _ = project_with_edge
    attr_ops.set_attribute(a.id, "description", "High price level", root=root)
    ch, _ = ch_ops.open_challenge(a.id, "Description is vague.", attribute="description", root=root)

    assert ch.target_attribute == "description"
    assert ch.target_id == a.id
    assert ch.state == "open"

    from latris.schema import DescriptionSet

    # The description store is untouched — no per-attribute maturity to flip.
    desc = load_model(DescriptionSet, root / "substrate" / "attributes" / "descriptions.yaml")
    target_entry = next(e for e in desc.entries if e.target_id == a.id)
    assert target_entry.value == "High price level"
