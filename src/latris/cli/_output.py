"""Machine-readable CLI output — the global ``latris --json`` flag.

With ``--json``, commands that support it print exactly one JSON object to
stdout instead of rich text: ``{"result": ..., "commit_sha": ...}`` for
mutations (the same shape the server routes return), ``{"result": [...]}``
for listings. Errors print ``{"error": ..., "type": ...}`` with the usual
exit codes (see ``_errors.handle_cli_errors``). Built for agents and the
hosted MCP server, which drive the CLI as a subprocess.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

_json_mode = False


def set_json_mode(enabled: bool) -> None:
    global _json_mode
    _json_mode = enabled


def json_mode() -> bool:
    return _json_mode


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def write_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(_plain(payload), ensure_ascii=False, default=str) + "\n")


def emit(result: Any, *, human: Callable[[], None], commit_sha: str | None = None) -> None:
    """Print ``result`` as JSON in ``--json`` mode, otherwise run ``human``."""
    if not _json_mode:
        human()
        return
    payload: dict[str, Any] = {"result": result}
    if commit_sha is not None:
        payload["commit_sha"] = commit_sha
    write_json(payload)
