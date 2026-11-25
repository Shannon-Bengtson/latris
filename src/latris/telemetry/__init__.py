"""Telemetry emission — one envelope, two backends, never fatal.

See ``docs/engineering/TELEMETRY.md``. The local backend appends to
``.graph-tooling/telemetry.jsonl`` (gitignored — behavioural data does not
belong in shared project history). The HTTP backend posts to the hosted
telemetry service when the project config enables upload; it is used by the
in-container server path, not by the CLI (CLI telemetry is deferred).
"""

from latris.telemetry.emitter import emit

__all__ = ["emit"]
