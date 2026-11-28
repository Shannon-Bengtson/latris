"""Every CLI command, generically: its ``--help`` works, and a bad argument fails cleanly.

Walks the whole command tree, so a new command is covered the moment it is
registered. A command that takes a required argument is invoked with a value
that names nothing, in a fresh empty project: it must exit non-zero with a
message, never with an unhandled Python exception (a traceback, to the user).
Commands whose argument is free text (a label, a question) legitimately accept
any value; they are listed in ``_ACCEPTS_ANY_TEXT`` and must still not crash.
"""

from __future__ import annotations

from pathlib import Path

import keyring
import keyring.backends.fail
import pytest
import typer.main
from typer.testing import CliRunner

from latris.ai.adapters.mock_adapter import MockAdapter
from latris.ai.adapters.mock_fixtures import register_gui_defaults
from latris.cli.app import app

runner = CliRunner()

BAD = "zz-no-such-thing"


def _commands() -> list[tuple[tuple[str, ...], object]]:
    out: list[tuple[tuple[str, ...], object]] = []

    def walk(cmd, path: tuple[str, ...]) -> None:
        subs = getattr(cmd, "commands", None)
        if subs:
            for name, sub in subs.items():
                walk(sub, (*path, name))
        else:
            out.append((path, cmd))

    walk(typer.main.get_command(app), ())
    return out


_ALL = _commands()


def _required_args(cmd) -> list:
    return [p for p in cmd.params if p.param_type_name == "argument" and p.required]


_WITH_ARGS = [(path, cmd) for path, cmd in _ALL if _required_args(cmd)]

# Commands whose required argument is free text, so any value is a valid one.
_ACCEPTS_ANY_TEXT = {
    "project set-question",  # the question
    "node add",  # the label
    "assumption add",  # the statement
    "question add",  # the question
    "finding add",  # the statement
    "version milestone",  # the milestone's name
    "version alternative",  # the alternative's name
}


def test_the_walk_finds_the_commands() -> None:
    names = {" ".join(path) for path, _ in _ALL}
    assert {"init", "node add", "ai call draft", "sync login"} <= names
    assert {" ".join(path) for path, _ in _WITH_ARGS} >= _ACCEPTS_ANY_TEXT


@pytest.mark.parametrize(("path", "cmd"), _ALL, ids=[" ".join(p) for p, _ in _ALL])
def test_help_exits_zero(path: tuple[str, ...], cmd) -> None:
    result = runner.invoke(app, [*path, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


@pytest.fixture
def _offline(monkeypatch: pytest.MonkeyPatch):
    """Mock AI with the placeholder responses, and a keyring that refuses
    everything, so no command reaches a model or the machine's real keyring."""
    monkeypatch.setenv("LATRIS_AI_MOCK", "1")
    MockAdapter.reset_shared()
    register_gui_defaults()
    previous = keyring.get_keyring()
    keyring.set_keyring(keyring.backends.fail.Keyring())
    yield
    keyring.set_keyring(previous)
    MockAdapter.reset_shared()


@pytest.mark.parametrize(("path", "cmd"), _WITH_ARGS, ids=[" ".join(p) for p, _ in _WITH_ARGS])
def test_bad_argument_fails_cleanly(
    path: tuple[str, ...], cmd, empty_project_root: Path, monkeypatch: pytest.MonkeyPatch, _offline
) -> None:
    monkeypatch.chdir(empty_project_root)
    args: list[str] = []
    for param in _required_args(cmd):
        args += [BAD] * (param.nargs if param.nargs and param.nargs > 0 else 1)
    result = runner.invoke(app, [*path, *args], input="")

    crashed = result.exception if not isinstance(result.exception, SystemExit) else None
    assert crashed is None, f"`latris {' '.join(path)} {' '.join(args)}` raised {crashed!r}"
    if " ".join(path) in _ACCEPTS_ANY_TEXT:
        return
    assert result.exit_code != 0, f"accepted {BAD!r}:\n{result.output}"
    assert result.output.strip(), "failed without saying why"
