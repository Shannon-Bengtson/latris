"""Keyring-backed store for sync credentials + the server URL.

Mirrors :mod:`latris.ai.credentials`: secrets live only in the OS
keyring (Windows Credential Manager / macOS Keychain / Linux Secret
Service), never on disk. The non-secret server URL and cached account JSON
also live here so the per-project backend can read them without a separate
app-level config mechanism.
"""

from __future__ import annotations

import contextlib
import json

import keyring

SERVICE = "latris-sync"

_SERVER_URL = "server_url"
_SESSION = "session"
_GITEA_TOKEN = "gitea_token"
_GITEA_USERNAME = "gitea_username"
_ACCOUNT = "account"
_LAST_VALIDATED = "last_validated"  # ISO timestamp of the last successful online re-check

_ALL_KEYS = (_SERVER_URL, _SESSION, _GITEA_TOKEN, _GITEA_USERNAME, _ACCOUNT, _LAST_VALIDATED)


def _get(key: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, key)
    except Exception:  # noqa: BLE001 — keyring backend issues must not crash callers
        return None


def _set(key: str, value: str) -> None:
    keyring.set_password(SERVICE, key, value)


def _del(key: str) -> None:
    with contextlib.suppress(Exception):  # deleting a missing key is fine
        keyring.delete_password(SERVICE, key)


def get_server_url() -> str | None:
    return _get(_SERVER_URL)


def set_server_url(url: str) -> None:
    _set(_SERVER_URL, url.rstrip("/"))


def get_session_token() -> str | None:
    return _get(_SESSION)


def get_gitea_token() -> str | None:
    return _get(_GITEA_TOKEN)


def get_gitea_username() -> str | None:
    return _get(_GITEA_USERNAME)


def get_account() -> dict | None:
    raw = _get(_ACCOUNT)
    return json.loads(raw) if raw else None


def is_logged_in() -> bool:
    return bool(get_session_token())


def store_session(
    *,
    server_url: str,
    session_token: str,
    gitea_token: str,
    gitea_username: str,
    account: dict,
) -> None:
    _set(_SERVER_URL, server_url.rstrip("/"))
    _set(_SESSION, session_token)
    _set(_GITEA_TOKEN, gitea_token)
    _set(_GITEA_USERNAME, gitea_username)
    _set(_ACCOUNT, json.dumps(account))


def update_session_token(token: str) -> None:
    _set(_SESSION, token)


def update_gitea_token(token: str) -> None:
    _set(_GITEA_TOKEN, token)


def update_cached_account(account: dict) -> None:
    """Replace the cached account JSON (e.g. after a profile edit)."""
    _set(_ACCOUNT, json.dumps(account))


def get_last_validated() -> str | None:
    return _get(_LAST_VALIDATED)


def set_last_validated(iso: str) -> None:
    _set(_LAST_VALIDATED, iso)


def clear() -> None:
    for key in _ALL_KEYS:
        _del(key)
