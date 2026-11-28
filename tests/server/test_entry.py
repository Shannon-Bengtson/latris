"""The server start-up entry points: ``python -m latris.server`` and the packaged ``entry``.

``uvicorn.run`` is replaced with a recorder, so nothing binds a port.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI

from latris.ai import credentials
from latris.repo.layout import ProjectPaths
from latris.server import __main__ as server_main
from latris.server import entry


@pytest.fixture
def uvicorn_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, dict]]:
    calls: list[tuple[object, dict]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    return calls


@pytest.fixture
def no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LATRIS_SERVER_TOKEN", raising=False)


def _argv(monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["latris-server", *args])


def _stdout_json(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


# ── python -m latris.server ──────────────────────────────────────────────────


def test_main_defaults_to_loopback_port_8741(
    monkeypatch, uvicorn_calls, no_token, capsys, two_node_project_root: Path
) -> None:
    monkeypatch.chdir(two_node_project_root)
    _argv(monkeypatch)
    server_main.main()

    [(app, kw)] = uvicorn_calls
    assert isinstance(app, FastAPI)
    assert kw == {"host": "127.0.0.1", "port": 8741}
    assert "WARNING" not in capsys.readouterr().err


def test_main_passes_host_port_and_project_root(
    monkeypatch, uvicorn_calls, no_token, capsys, two_node_project_root: Path, tmp_path: Path
) -> None:
    seen: dict = {}
    real_create = server_main.create_app

    def spy(project_root=None):
        seen["root"] = project_root
        return real_create(project_root=project_root)

    monkeypatch.setattr(server_main, "create_app", spy)
    monkeypatch.chdir(tmp_path)  # not a project: the explicit root must be what's used
    _argv(monkeypatch, "--project-root", str(two_node_project_root), "--host", "0.0.0.0", "--port", "9001")
    server_main.main()

    assert seen["root"] == two_node_project_root
    [(_, kw)] = uvicorn_calls
    assert kw == {"host": "0.0.0.0", "port": 9001}
    # Binding beyond loopback with no token warns before serving.
    assert "WARNING" in capsys.readouterr().err


def test_main_rejects_a_non_integer_port(monkeypatch, uvicorn_calls) -> None:
    _argv(monkeypatch, "--port", "eighty")
    with pytest.raises(SystemExit) as exc:
        server_main.main()
    assert exc.value.code == 2
    assert uvicorn_calls == []


# ── entry: server mode ───────────────────────────────────────────────────────


def test_entry_server_mode_is_the_default(
    monkeypatch, uvicorn_calls, no_token, capsys, two_node_project_root: Path
) -> None:
    _argv(monkeypatch, "--project-root", str(two_node_project_root), "--port", "8800")
    entry.main()

    [(app, kw)] = uvicorn_calls
    assert isinstance(app, FastAPI)
    assert kw == {"host": "127.0.0.1", "port": 8800}
    assert "WARNING" not in capsys.readouterr().err


def test_entry_server_mode_warns_when_exposed_without_token(
    monkeypatch, uvicorn_calls, no_token, capsys, two_node_project_root: Path
) -> None:
    _argv(monkeypatch, "--mode", "server", "--project-root", str(two_node_project_root), "--host", "0.0.0.0")
    entry.main()
    assert uvicorn_calls[0][1]["host"] == "0.0.0.0"
    assert "no access token" in capsys.readouterr().err


def test_entry_server_mode_quiet_when_exposed_with_token(
    monkeypatch, uvicorn_calls, capsys, two_node_project_root: Path
) -> None:
    monkeypatch.setenv("LATRIS_SERVER_TOKEN", "t" * 32)
    _argv(monkeypatch, "--project-root", str(two_node_project_root), "--host", "0.0.0.0")
    entry.main()
    assert len(uvicorn_calls) == 1
    assert "WARNING" not in capsys.readouterr().err


def test_entry_rejects_an_unknown_mode(monkeypatch, uvicorn_calls) -> None:
    _argv(monkeypatch, "--mode", "desktop")
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 2
    assert uvicorn_calls == []


# ── entry: init mode ─────────────────────────────────────────────────────────


def test_entry_init_creates_a_project_and_prints_its_root(
    monkeypatch, capsys, tmp_path: Path, git_identity
) -> None:
    target = tmp_path / "coast"
    _argv(monkeypatch, "--mode", "init", "--path", str(target), "--statement", "Why is water quality falling?", "--name", "Coast")
    entry.main()

    out = _stdout_json(capsys)
    assert out == {"ok": True, "root": str(target.resolve())}
    assert ProjectPaths(target.resolve()).state_dir.is_dir()


def test_entry_init_reports_failure_as_json_and_exits_1(
    monkeypatch, capsys, tmp_path: Path, git_identity
) -> None:
    target = tmp_path / "coast"
    _argv(monkeypatch, "--mode", "init", "--path", str(target), "--statement", "Q?")
    entry.main()
    capsys.readouterr()

    # A second init on the same directory is refused; the error arrives as JSON.
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 1
    out = _stdout_json(capsys)
    assert out["ok"] is False
    assert out["error"]


@pytest.mark.parametrize("missing", [["--path", "x"], ["--statement", "Q?"], []])
def test_entry_init_requires_path_and_statement(monkeypatch, capsys, missing) -> None:
    _argv(monkeypatch, "--mode", "init", *missing)
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 2
    assert "--path and --statement are required" in capsys.readouterr().err


# ── entry: key modes ─────────────────────────────────────────────────────────


def test_entry_list_keys_prints_providers_and_default(monkeypatch, capsys) -> None:
    rows = [{"provider": "gemini", "source": "env", "env_var": "GEMINI_API_KEY"}]
    monkeypatch.setattr(credentials, "list_providers", lambda: rows)
    _argv(monkeypatch, "--mode", "list-keys")
    entry.main()

    out = _stdout_json(capsys)
    from latris.ai.config import DEFAULT_MODEL

    assert out["ok"] is True
    assert out["providers"] == rows
    assert out["default_provider"] == DEFAULT_MODEL.split("/")[0]
    assert "/" not in out["default_provider"]


def test_entry_list_keys_failure_is_json_with_empty_providers(monkeypatch, capsys) -> None:
    def boom():
        raise RuntimeError("keyring locked")

    monkeypatch.setattr(credentials, "list_providers", boom)
    _argv(monkeypatch, "--mode", "list-keys")
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 1
    assert _stdout_json(capsys) == {"ok": False, "error": "keyring locked", "providers": []}


def test_entry_set_key_reads_the_key_from_stdin(monkeypatch, capsys) -> None:
    stored: list[tuple[str, str]] = []
    monkeypatch.setattr(credentials, "set_key", lambda p, v: stored.append((p, v)))
    monkeypatch.setattr(sys, "stdin", io.StringIO("  sk-test-value\n"))
    _argv(monkeypatch, "--mode", "set-key", "--provider", "anthropic")
    entry.main()

    assert stored == [("anthropic", "sk-test-value")]  # stripped, and never from argv
    assert _stdout_json(capsys) == {"ok": True}


def test_entry_set_key_refuses_empty_stdin(monkeypatch, capsys) -> None:
    stored: list = []
    monkeypatch.setattr(credentials, "set_key", lambda p, v: stored.append((p, v)))
    monkeypatch.setattr(sys, "stdin", io.StringIO("   \n"))
    _argv(monkeypatch, "--mode", "set-key", "--provider", "anthropic")
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 1
    assert stored == []
    assert _stdout_json(capsys) == {"ok": False, "error": "No key provided on stdin"}


def test_entry_set_key_reports_a_keyring_error(monkeypatch, capsys) -> None:
    def boom(provider, value):
        raise RuntimeError("no backend")

    monkeypatch.setattr(credentials, "set_key", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO("sk-x"))
    _argv(monkeypatch, "--mode", "set-key", "--provider", "openai")
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 1
    out = _stdout_json(capsys)
    assert out == {"ok": False, "error": "no backend"}
    assert "sk-x" not in json.dumps(out)


def test_entry_set_key_requires_a_provider(monkeypatch, capsys) -> None:
    _argv(monkeypatch, "--mode", "set-key")
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 2
    assert "--provider is required" in capsys.readouterr().err
