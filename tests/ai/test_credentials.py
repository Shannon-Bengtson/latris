"""Credential facade tests — keyring is swapped for an in-memory backend so
nothing touches the real OS credential store.
"""

from __future__ import annotations

import os

import keyring
import pytest
from keyring.backend import KeyringBackend

from latris.ai import credentials as creds


class InMemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._store:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._store[key]


@pytest.fixture
def in_memory_keyring(monkeypatch: pytest.MonkeyPatch) -> InMemoryKeyring:
    fake = InMemoryKeyring()
    original = keyring.get_keyring()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(original)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in creds.PROVIDER_ENV.values():
        monkeypatch.delenv(var, raising=False)


def test_set_and_get_key_roundtrip(in_memory_keyring, clean_env) -> None:
    creds.set_key("anthropic", "sk-test-123")
    assert creds.get_key("anthropic") == "sk-test-123"


def test_get_key_prefers_env_over_keyring(
    in_memory_keyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creds.set_key("anthropic", "from-keyring")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert creds.get_key("anthropic") == "from-env"


def test_get_key_returns_none_when_absent(in_memory_keyring, clean_env) -> None:
    assert creds.get_key("openai") is None


def test_require_key_raises_when_absent(in_memory_keyring, clean_env) -> None:
    with pytest.raises(creds.CredentialError, match="no API key"):
        creds.require_key("openai")


def test_require_key_returns_value_when_present(in_memory_keyring, clean_env) -> None:
    creds.set_key("openai", "sk-123")
    assert creds.require_key("openai") == "sk-123"


def test_unset_key_removes(in_memory_keyring, clean_env) -> None:
    creds.set_key("groq", "x")
    assert creds.unset_key("groq") is True
    assert creds.get_key("groq") is None
    # Second unset returns False (nothing to delete).
    assert creds.unset_key("groq") is False


def test_set_key_refuses_empty(in_memory_keyring) -> None:
    with pytest.raises(ValueError, match="empty"):
        creds.set_key("anthropic", "")


def test_list_providers_shows_source(
    in_memory_keyring,
    clean_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creds.set_key("anthropic", "from-keyring")
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    listed = creds.list_providers()
    by_provider = {p["provider"]: p for p in listed}
    assert by_provider["anthropic"]["source"] == "keyring"
    assert by_provider["openai"]["source"] == "env"
    # Values are NEVER included
    for entry in listed:
        assert "value" not in entry
        assert "from-keyring" not in str(entry)
        assert "from-env" not in str(entry)


def test_key_in_env_stages_and_cleans_up(
    in_memory_keyring,
    clean_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creds.set_key("anthropic", "sk-test")
    assert os.environ.get("ANTHROPIC_API_KEY") is None

    with creds.key_in_env(["anthropic"]):
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"

    # Cleaned up after the context exits.
    assert os.environ.get("ANTHROPIC_API_KEY") is None


def test_key_in_env_does_not_stomp_preexisting(
    in_memory_keyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "preexisting")
    creds.set_key("anthropic", "from-keyring")
    with creds.key_in_env(["anthropic"]):
        assert os.environ["ANTHROPIC_API_KEY"] == "preexisting"
    # Still there after exit (we didn't set it, we don't pop it).
    assert os.environ["ANTHROPIC_API_KEY"] == "preexisting"
