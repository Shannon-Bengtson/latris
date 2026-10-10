"""Sync transport operations — full collaboration round-trips via a local bare remote."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from latris.operations import sync
from latris.operations.nodes import add_node, list_nodes, rename_node
from latris.repo import git
from latris.sync.client import SyncClientError


def _bare(tmp_path: Path, name: str = "remote.git") -> Path:
    bare = tmp_path / name
    git.init_bare(bare)
    return bare


def test_set_remote_and_url(empty_project_root: Path, tmp_path: Path) -> None:
    assert sync.remote_url(root=empty_project_root) is None
    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=empty_project_root)
    assert sync.remote_url(root=empty_project_root) == str(bare)

    # repointing an existing remote is idempotent
    bare2 = _bare(tmp_path, "remote2.git")
    sync.set_remote(str(bare2), root=empty_project_root)
    assert sync.remote_url(root=empty_project_root) == str(bare2)


def test_push_without_remote_errors(empty_project_root: Path) -> None:
    with pytest.raises(sync.SyncError):
        sync.push(root=empty_project_root)


def test_push_then_clone_sees_data(two_node_project_root: Path, tmp_path: Path) -> None:
    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=two_node_project_root)
    sync.push(root=two_node_project_root)

    bob = tmp_path / "bob"
    git.clone(str(bare), bob)
    labels = {n.label for n in list_nodes(root=bob)}
    assert {"Price", "Demand"} <= labels


def test_pull_fast_forward_gets_collaborator_change(two_node_project_root: Path, tmp_path: Path) -> None:
    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=two_node_project_root)
    sync.push(root=two_node_project_root)

    bob = tmp_path / "bob"
    git.clone(str(bare), bob)
    add_node("Widget", root=bob)
    sync.push(root=bob)

    sync.pull(root=two_node_project_root)
    labels = {n.label for n in list_nodes(root=two_node_project_root)}
    assert "Widget" in labels


def test_pull_conflict_raises_syncerror(two_node_project_root: Path, tmp_path: Path) -> None:
    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=two_node_project_root)
    sync.push(root=two_node_project_root)

    bob = tmp_path / "bob"
    git.clone(str(bare), bob)

    # Diverge on the same entity's label — guarantees a conceptual.yaml conflict.
    rename_node("Price", "Cost", root=two_node_project_root)
    sync.push(root=two_node_project_root)
    rename_node("Price", "Charge", root=bob)

    with pytest.raises(sync.SyncError):
        sync.pull(root=bob)


def test_status_reports_state(two_node_project_root: Path, tmp_path: Path) -> None:
    s = sync.status(root=two_node_project_root)
    assert s["url"] is None
    assert s["branch"] == "main"

    bare = _bare(tmp_path)
    sync.set_remote(str(bare), root=two_node_project_root)
    sync.push(root=two_node_project_root)

    s = sync.status(root=two_node_project_root)
    assert s["url"] == str(bare)
    assert s["ahead"] == 0
    assert s["behind"] == 0


# -- Access re-validation (the launch-time gate) ------------------------------


class _FakeClient:
    """Stands in for SyncClient.validate — returns an account or raises."""

    def __init__(self, *, result=None, error=None) -> None:
        self._result = result
        self._error = error

    def validate(self):
        if self._error is not None:
            raise self._error
        return self._result


def _patch_creds(monkeypatch, **overrides) -> dict:
    """Patch credentials.* used by validate_access; record calls. Defaults to logged-in."""
    calls: dict = {"cleared": False, "cached": None, "stamped": None}
    monkeypatch.setattr(sync.credentials, "is_logged_in", lambda: overrides.get("logged_in", True))
    monkeypatch.setattr(sync.credentials, "get_account", lambda: overrides.get("account"))
    monkeypatch.setattr(sync.credentials, "get_last_validated", lambda: overrides.get("last_validated"))
    monkeypatch.setattr(sync.credentials, "set_last_validated", lambda iso: calls.update(stamped=iso))
    monkeypatch.setattr(sync.credentials, "update_cached_account", lambda a: calls.update(cached=a))
    monkeypatch.setattr(sync.credentials, "clear", lambda: calls.update(cleared=True))
    return calls


def test_validate_access_anon_when_not_logged_in(monkeypatch) -> None:
    _patch_creds(monkeypatch, logged_in=False)
    assert sync.validate_access() == {"state": "anon", "account": None}


def test_validate_access_valid_refreshes_cache_and_stamp(monkeypatch) -> None:
    acct = {"id": "acct_1", "email": "a@x.io"}
    calls = _patch_creds(monkeypatch)
    monkeypatch.setattr(sync, "_client", lambda **kw: _FakeClient(result=acct))
    res = sync.validate_access()
    assert res == {"state": "valid", "account": acct}
    assert calls["cached"] == acct
    assert calls["stamped"] is not None


def test_validate_access_revoked_clears_credentials(monkeypatch) -> None:
    calls = _patch_creds(monkeypatch)
    monkeypatch.setattr(
        sync, "_client", lambda **kw: _FakeClient(error=SyncClientError("nope", status_code=401))
    )
    assert sync.validate_access() == {"state": "revoked", "account": None}
    assert calls["cleared"] is True


def test_validate_access_offline_within_grace(monkeypatch) -> None:
    acct = {"id": "acct_1"}
    _patch_creds(monkeypatch, account=acct, last_validated=sync._now_iso())
    monkeypatch.setattr(
        sync, "_client", lambda **kw: _FakeClient(error=SyncClientError("offline", status_code=None))
    )
    res = sync.validate_access()
    assert res["state"] == "offline_ok"
    assert res["account"] == acct


def test_validate_access_offline_past_grace_expires(monkeypatch) -> None:
    old = (datetime.now(UTC) - timedelta(days=sync.GRACE_DAYS + 1)).isoformat()
    _patch_creds(monkeypatch, account={"id": "x"}, last_validated=old)
    monkeypatch.setattr(sync, "_client", lambda **kw: _FakeClient(error=SyncClientError("offline")))
    assert sync.validate_access()["state"] == "offline_expired"
