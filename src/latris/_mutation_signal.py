"""Cross-layer signal that a server-initiated mutation just happened.

Lives at the package root (alongside :mod:`latris.perf`) so
``operations/commit.py`` can fire it from ``auto_commit`` without
importing from the ``server/`` layer. The file watcher reads this
signal to suppress redundant ``state_changed`` broadcasts after the
GUI's own mutation response has already rehydrated its store.

The mechanism is a 2-second wall-clock window: any file change
detected within :data:`SUPPRESS_SECONDS` of the last
:func:`mark_own_mutation` call is treated as our own write and
silently dropped. The window is intentionally short — external
mutations (CLI runs, another editor) still get a broadcast as soon
as the window expires.
"""

from __future__ import annotations

import time

SUPPRESS_SECONDS = 2.0

_last_own_mutation: float = 0.0


def mark_own_mutation() -> None:
    """Stamp the suppression window. Called by ``auto_commit`` on a real commit."""
    global _last_own_mutation  # noqa: PLW0603
    _last_own_mutation = time.monotonic()


def is_suppressed() -> bool:
    """True if a server mutation happened within the suppression window."""
    return (time.monotonic() - _last_own_mutation) < SUPPRESS_SECONDS
