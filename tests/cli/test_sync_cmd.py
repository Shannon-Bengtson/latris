"""CLI tests for `latris sync login` / `latris sync share`.

Mocked at the operations boundary (`latris.operations.sync`), consistent
with this CLI layer's own contract: one parse, one call into operations,
one print — these tests verify exactly that, not operations.sync's own
internals (login_verify/share's SyncClient + git plumbing has no existing
operations-level test coverage either; out of scope for a CLI wrapper).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from latris.cli.app import app
from latris.operations import sync as ops

runner = CliRunner()


def test_login_without_code_requests_one(empty_project_root: Path, monkeypatch) -> None:
    monkeypatch.chdir(empty_project_root)
    calls = {}
    monkeypatch.setattr(
        ops, "login_request_code", lambda server, email, intent: calls.update(server=server, email=email, intent=intent)
    )
    result = runner.invoke(app, ["sync", "login", "--email", "a@x.com"])
    assert result.exit_code == 0
    assert calls == {"server": "https://sync.latris.app", "email": "a@x.com", "intent": "auto"}
    assert "code sent" in result.stdout
    assert "--code" in result.stdout


def test_login_with_code_verifies(empty_project_root: Path, monkeypatch) -> None:
    monkeypatch.chdir(empty_project_root)
    seen = {}

    def _verify(server, email, code, device, **kwargs):
        seen.update(server=server, email=email, code=code, device=device, **kwargs)
        return {"email": email, "display_name": "A X"}

    monkeypatch.setattr(ops, "login_verify", _verify)
    result = runner.invoke(app, ["sync", "login", "--email", "a@x.com", "--code", "123456"])
    assert result.exit_code == 0
    assert seen["email"] == "a@x.com"
    assert seen["code"] == "123456"
    assert seen["device"] == "Latris CLI"
    assert "signed in" in result.stdout
    assert "A X" in result.stdout
    assert "sync share" in result.stdout


def test_login_failure_exits_cleanly(empty_project_root: Path, monkeypatch) -> None:
    monkeypatch.chdir(empty_project_root)
    monkeypatch.setattr(
        ops, "login_request_code", lambda *a, **k: (_ for _ in ()).throw(ops.SyncError("bad email"))
    )
    result = runner.invoke(app, ["sync", "login", "--email", "nope"])
    assert result.exit_code == 1
    assert "bad email" in result.stdout.lower() or "bad email" in str(result.exception)


def test_share_prints_confirmation_and_app_link(empty_project_root: Path, monkeypatch) -> None:
    monkeypatch.chdir(empty_project_root)
    monkeypatch.setattr(ops, "current_account", lambda: {"email": "a@x.com"})
    monkeypatch.setattr(
        ops, "share", lambda name, **kwargs: {"id": "proj_123", "name": name, "clone_url": "https://x/y.git"}
    )
    result = runner.invoke(app, ["sync", "share", "My Project"])
    assert result.exit_code == 0
    assert "shared" in result.stdout.lower()
    assert "proj_123" in result.stdout
    assert "https://app.latris.app" in result.stdout
    assert "a@x.com" in result.stdout


def test_share_without_account_omits_email_hint(empty_project_root: Path, monkeypatch) -> None:
    monkeypatch.chdir(empty_project_root)
    monkeypatch.setattr(ops, "current_account", lambda: None)
    monkeypatch.setattr(ops, "share", lambda name, **kwargs: {"id": "proj_123", "name": name})
    result = runner.invoke(app, ["sync", "share", "My Project"])
    assert result.exit_code == 0
    assert "sign in with" not in result.stdout


def test_share_requires_login(empty_project_root: Path, monkeypatch) -> None:
    monkeypatch.chdir(empty_project_root)
    monkeypatch.setattr(ops, "current_account", lambda: None)
    monkeypatch.setattr(
        ops, "share", lambda name, **kwargs: (_ for _ in ()).throw(ops.SyncError("not signed in to Latris"))
    )
    result = runner.invoke(app, ["sync", "share", "My Project"])
    assert result.exit_code == 1
