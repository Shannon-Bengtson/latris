"""Project membership — the advisory governance record committed to the repo.

This is the in-repo mirror of the sync control plane's authoritative
membership table. It travels *with* the model so the project carries its own
auditable record of who held what role. The control plane (not this file)
drives the actual Gitea access-control; ``members.yaml`` is advisory.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from latris.schema.common import HumanActor, _Base, now_utc

MemberRole = Literal["owner", "collaborator", "reviewer"]


class MemberRecord(_Base):
    actor: HumanActor
    role: MemberRole
    # Stable Latris account id (``acct_<ULID>``) — the bridge from
    # git-committer attribution to a first-class sync account. Optional so
    # invited-but-not-yet-registered members can still be recorded.
    account_id: str | None = None
    added_by: HumanActor
    added_at: datetime = Field(default_factory=now_utc)


class MembersFile(_Base):
    members: list[MemberRecord] = Field(default_factory=list)
