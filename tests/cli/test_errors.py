"""Tests for the CLI error handling decorator."""

from __future__ import annotations

import pytest
import typer

from latris.ai.adapters.base import LLMCallError
from latris.ai.credentials import CredentialError
from latris.cli._errors import handle_cli_errors
from latris.operations._resolve import ResolveError
from latris.repo.git import GitError, IdentityError
from latris.repo.project import NotAProjectError


def _make_raiser(exc):
    """Create a decorated function that raises the given exception."""

    @handle_cli_errors
    def fn():
        raise exc

    return fn


def test_not_a_project_exits_1():
    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(NotAProjectError("no project"))()
    assert exc_info.value.exit_code == 1


def test_resolve_error_exits_1():
    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(ResolveError("ambiguous"))()
    assert exc_info.value.exit_code == 1


def test_identity_error_exits_1():
    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(IdentityError("no name"))()
    assert exc_info.value.exit_code == 1


def test_git_error_exits_1():
    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(GitError("failed"))()
    assert exc_info.value.exit_code == 1


def test_credential_error_exits_1():
    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(CredentialError("no key"))()
    assert exc_info.value.exit_code == 1


def test_llm_call_error_exits_1():
    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(LLMCallError("model down"))()
    assert exc_info.value.exit_code == 1


def test_value_error_exits_2():
    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(ValueError("bad input"))()
    assert exc_info.value.exit_code == 2


def test_pydantic_validation_error_is_friendly(capsys):
    """A pydantic error reads as 'field: what went wrong (got x)' — no pydantic internals or URLs."""
    from typing import Literal

    from pydantic import BaseModel, Field, ValidationError

    class M(BaseModel):
        direction: Literal["higher", "lower"]
        weight: float = Field(gt=0)

    try:
        M(direction="minimise", weight=0)
    except ValidationError as exc:
        raised = exc

    with pytest.raises(typer.Exit) as exc_info:
        _make_raiser(raised)()
    assert exc_info.value.exit_code == 2
    out = capsys.readouterr().out
    assert "pydantic" not in out and "http" not in out
    assert "direction" in out and "'higher' or 'lower'" in out and "'minimise'" in out
    assert "weight" in out and "greater than 0" in out


def test_pydantic_value_error_prefix_stripped(capsys):
    """Custom validators' messages lose pydantic's 'Value error, ' prefix."""
    from pydantic import BaseModel, ValidationError, field_validator

    class M(BaseModel):
        k: int | None = None

        @field_validator("k")
        @classmethod
        def needs_k(cls, v):
            raise ValueError("a vote gate needs k")

    try:
        M(k=1)
    except ValidationError as exc:
        raised = exc

    with pytest.raises(typer.Exit):
        _make_raiser(raised)()
    out = capsys.readouterr().out
    assert "Value error," not in out and "a vote gate needs k" in out


def test_unhandled_exception_propagates():
    """Exceptions not listed in the decorator should propagate normally."""
    with pytest.raises(RuntimeError, match="unexpected"):
        _make_raiser(RuntimeError("unexpected"))()


def test_successful_function_returns_value():
    @handle_cli_errors
    def fn():
        return 42

    assert fn() == 42
