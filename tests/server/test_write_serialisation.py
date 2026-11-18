"""Concurrent mutating requests must not lose updates or collide on git.

Regression: sync routes run on a thread pool, and every mutation is
load → change → dump → git add → git commit. Twelve parallel fault-tree
probability writes used to end with most failing (git ``index.lock``, a shared
``.tmp`` file deleted under another writer) and only a few values saved.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from latris.operations import fault_tree as ft
from latris.operations import nodes as node_ops
from latris.operations import write_lock
from latris.operations.batch import batch
from latris.operations.init import init_project
from latris.repo import git
from latris.server.app import create_app

N = 12


@pytest.fixture
def project(tmp_path: Path, git_identity) -> Path:
    root = tmp_path / "proj"
    init_project(root, statement="Why does the pump fail?")
    with batch(root, subject="Add events"):
        for i in range(N):
            node_ops.add_node(f"E{i}", root=root)
            ft.set_event(f"E{i}", "basic_event", root=root)
    return root


def test_parallel_writes_all_land(project: Path) -> None:
    with TestClient(create_app(project_root=project)) as client:

        def post(i: int) -> int:
            return client.post("/api/ft/probability", json={"node": f"E{i}", "probability": 0.01 * (i + 1)}).status_code

        with ThreadPoolExecutor(N) as pool:
            codes = list(pool.map(post, range(N)))

    assert codes == [200] * N
    saved = sorted(round(e.probability, 6) for e in ft.get_probabilities(root=project).entries)
    assert saved == [round(0.01 * (i + 1), 6) for i in range(N)]
    assert git.run_git(["status", "--porcelain"], cwd=project).stdout.strip() == ""
    assert not list(project.rglob("*.tmp"))


def test_released_gives_the_lock_up_and_takes_it_back(project: Path) -> None:
    import asyncio

    async def run() -> None:
        async with write_lock.hold(project):
            assert write_lock.is_held(project)
            with write_lock.released():
                assert not write_lock.is_held(project)
                # Another request can take it meanwhile.
                async with write_lock.hold(project):
                    pass
            assert write_lock.is_held(project)
        assert not write_lock.is_held(project)

    asyncio.run(run())
