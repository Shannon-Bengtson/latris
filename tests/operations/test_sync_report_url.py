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
