"""Shared CLI error handling — one place to convert backend exceptions to typer Exit."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

import typer
from rich.console import Console

from latris.ai.adapters.base import LLMCallError
from latris.ai.credentials import CredentialError
from latris.operations._resolve import ResolveError
from latris.operations.sync import SyncError
from latris.repo.git import GitError, IdentityError
from latris.repo.project import NotAProjectError

console = Console()

F = TypeVar("F", bound=Callable)


def handle_cli_errors(fn: F) -> F:
    """Decorator: translate backend exceptions into clean typer exits."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotAProjectError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(code=1) from None
        except ResolveError as exc:
            console.print(f"[red]resolve error:[/red] {exc}")
            raise typer.Exit(code=1) from None
        except IdentityError as exc:
            console.print(f"[red]identity error:[/red] {exc}")
            raise typer.Exit(code=1) from None
        except SyncError as exc:
            console.print(f"[red]sync error:[/red] {exc}")
            raise typer.Exit(code=1) from None
        except GitError as exc:
            console.print(f"[red]git error:[/red] {exc}")
            raise typer.Exit(code=1) from None
        except CredentialError as exc:
            console.print(f"[red]credential error:[/red] {exc}")
            raise typer.Exit(code=1) from None
        except LLMCallError as exc:
            # Message has already been scrubbed of API keys in the adapter.
            # `from None` suppresses the chained traceback so the original
            # provider exception (which may contain the key in a URL) doesn't
            # get printed by rich.
            console.print(f"[red]AI call failed:[/red] {exc}")
            raise typer.Exit(code=1) from None
        except ValueError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(code=2) from None

    return wrapper  # type: ignore[return-value]
