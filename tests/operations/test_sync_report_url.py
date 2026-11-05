from __future__ import annotations

from pathlib import Path

from latris.operations import sync as sync_ops
from latris.operations.init import init_project


def test_report_url_round_trips_through_git_config(tmp_path: Path, git_identity) -> None:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    assert sync_ops.report_url(root=root) is None
    sync_ops.set_report_url("https://app.latris.app/r/abc", root=root)
    assert sync_ops.report_url(root=root) == "https://app.latris.app/r/abc"
    sync_ops.set_report_url(None, root=root)
    assert sync_ops.report_url(root=root) is None
    # Unsetting twice is harmless.
    sync_ops.set_report_url(None, root=root)


def test_set_report_link_records_url(tmp_path: Path, git_identity, monkeypatch) -> None:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")

    class _Client:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def set_report_sharing(self, pid, enabled, pack):
            self.calls.append((pid, enabled, pack))
            return {"report_url": "https://app.test/r/abc" if enabled else None, "report_pack": pack or "client"}

    client = _Client()
    monkeypatch.setattr(sync_ops, "_client", lambda **kw: client)

    import pytest

    with pytest.raises(sync_ops.SyncError, match="not shared"):
        sync_ops.set_report_link(True, root=root)

    from latris.repo import git

    git.set_config(root, sync_ops.SYNC_PROJECT_ID_KEY, "proj_1")
    sync_ops.set_report_link(True, pack="review", root=root)
    assert client.calls == [("proj_1", True, "review")]
    assert sync_ops.report_url(root=root) == "https://app.test/r/abc"
    sync_ops.set_report_link(False, root=root)
    assert sync_ops.report_url(root=root) is None


def test_get_report_link_refreshes_local_copy(tmp_path: Path, git_identity, monkeypatch) -> None:
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    assert sync_ops.get_report_link(root=root) == {"report_url": None, "report_pack": None}

    class _Client:
        def get_project(self, pid):
            return {"id": pid, "report_url": "https://app.test/r/new", "report_pack": "review"}

    monkeypatch.setattr(sync_ops, "_client", lambda **kw: _Client())
    from latris.repo import git

    git.set_config(root, sync_ops.SYNC_PROJECT_ID_KEY, "proj_1")
    sync_ops.set_report_url("https://app.test/r/stale", root=root)
    assert sync_ops.get_report_link(root=root) == {"report_url": "https://app.test/r/new", "report_pack": "review"}
    assert sync_ops.report_url(root=root) == "https://app.test/r/new"
