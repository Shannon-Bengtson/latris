"""Shared CLI error handling — one place to convert backend exceptions to typer Exit."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

import typer
from rich.console import Console

from latris.ai.adapters.base import LLMCallError
from latris.ai.credentials import CredentialError
from latris.cli._output import json_mode, write_json
from latris.operations._resolve import ResolveError
from latris.operations.sync import SyncError
from latris.repo.git import GitError, IdentityError
from latris.repo.project import NotAProjectError

console = Console()

F = TypeVar("F", bound=Callable)


def _fail(label: str, exc: Exception, code: int) -> typer.Exit:
    """Report ``exc`` (as JSON in ``--json`` mode) and return the exit to raise."""
    if json_mode():
        write_json({"error": str(exc), "type": label})
    else:
        console.print(f"[red]{label}:[/red] {exc}")
    return typer.Exit(code=code)


def handle_cli_errors(fn: F) -> F:
    """Decorator: translate backend exceptions into clean typer exits."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotAProjectError as exc:
            raise _fail("error", exc, 1) from None
        except ResolveError as exc:
            raise _fail("resolve error", exc, 1) from None
        except IdentityError as exc:
            raise _fail("identity error", exc, 1) from None
        except SyncError as exc:
            raise _fail("sync error", exc, 1) from None
        except GitError as exc:
            raise _fail("git error", exc, 1) from None
        except CredentialError as exc:
            raise _fail("credential error", exc, 1) from None
        except LLMCallError as exc:
            # Message has already been scrubbed of API keys in the adapter.
            # `from None` suppresses the chained traceback so the original
            # provider exception (which may contain the key in a URL) doesn't
            # get printed by rich.
            raise _fail("AI call failed", exc, 1) from None
        except ValueError as exc:
            raise _fail("error", exc, 2) from None

    return wrapper  # type: ignore[return-value]
