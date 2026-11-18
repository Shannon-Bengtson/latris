"""One writer at a time per project, inside a process.

Every mutation is load → change → dump → ``git add`` → ``git commit``. Two of
those interleaving (the server runs sync routes on a thread pool) lose
updates, collide on git's ``index.lock``, or commit each other's staged files
under the wrong subject. The server holds this lock for the whole of each
mutating request (:func:`hold`), which makes every operation atomic without
touching each one.

A long model call shouldn't block every other edit, so the one place that
waits on an LLM gives the lock up for the duration (:func:`released`); the
operations it then applies re-read the files they change, so nothing read
before the call is written back stale.

The CLI is one process per command and doesn't take the lock.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from pathlib import Path

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
# Roots whose lock the current request holds. Context variables follow the
# request into the worker thread its sync route runs on.
_held: ContextVar[frozenset[str]] = ContextVar("latris_write_locks_held", default=frozenset())

_POLL_SECONDS = 0.005


def _key(root: Path) -> str:
    return str(Path(root).resolve())


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


@asynccontextmanager
async def hold(root: Path) -> AsyncIterator[None]:
    """Hold ``root``'s write lock from the event loop without blocking it.

    Polls rather than waiting in a worker thread: a waiter parked on a thread
    would use up the pool the lock's holder needs to finish its request.
    """
    key = _key(root)
    if key in _held.get():
        yield
        return
    lock = _lock_for(key)
    while not lock.acquire(blocking=False):
        await asyncio.sleep(_POLL_SECONDS)
    before = _held.get()
    _held.set(before | {key})
    try:
        yield
    finally:
        _held.set(before)
        lock.release()  # a plain Lock may be released from any thread


@contextmanager
def released() -> Iterator[None]:
    """Give up every write lock this request holds until the block ends.

    For waiting on something slow and external (a model call). A no-op
    outside a locked request.
    """
    keys = _held.get()
    if not keys:
        yield
        return
    locks = [_lock_for(k) for k in sorted(keys)]
    for lock in locks:
        lock.release()
    _held.set(frozenset())
    try:
        yield
    finally:
        for lock in locks:
            lock.acquire()
        _held.set(keys)


def is_held(root: Path) -> bool:
    """Whether the current request holds ``root``'s write lock (for tests)."""
    return _key(root) in _held.get()
