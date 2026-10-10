from __future__ import annotations

from pathlib import Path

from latris.repo.yaml_io import dump_model, load_model
from latris.schema import HumanActor, MemberRecord, MembersFile


def test_membersfile_roundtrip(tmp_path: Path) -> None:
    alice = HumanActor(name="Alice", email="alice@example.com")
    bob = HumanActor(name="Bob", email="bob@example.com")
    mf = MembersFile(
        members=[
            MemberRecord(actor=alice, account_id="acct_A", role="owner", added_by=alice),
            MemberRecord(actor=bob, account_id="acct_B", role="collaborator", added_by=alice),
        ]
    )
    path = tmp_path / "members.yaml"
    dump_model(mf, path)
    loaded = load_model(MembersFile, path)
    assert loaded == mf
    assert loaded.members[0].account_id == "acct_A"
    assert loaded.members[1].role == "collaborator"


def test_member_account_id_optional(tmp_path: Path) -> None:
    # an invited-but-unregistered member has no account_id yet
    alice = HumanActor(name="Alice", email="alice@example.com")
    invited = HumanActor(name="carol@example.com", email="carol@example.com")
    mf = MembersFile(members=[MemberRecord(actor=invited, role="collaborator", added_by=alice)])
    path = tmp_path / "members.yaml"
    dump_model(mf, path)
    assert load_model(MembersFile, path).members[0].account_id is None
