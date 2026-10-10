from __future__ import annotations

import pytest

from latris.sync import credentials


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> dict:
    store: dict[tuple[str, str], str] = {}

    def get(service: str, key: str):
        return store.get((service, key))

    def set_(service: str, key: str, value: str):
        store[(service, key)] = value

    def delete(service: str, key: str):
        if (service, key) in store:
            del store[(service, key)]
        else:
            raise KeyError(key)

    monkeypatch.setattr(credentials.keyring, "get_password", get)
    monkeypatch.setattr(credentials.keyring, "set_password", set_)
    monkeypatch.setattr(credentials.keyring, "delete_password", delete)
    return store


def test_store_and_read(fake_keyring: dict) -> None:
    assert credentials.is_logged_in() is False
    credentials.store_session(
        server_url="https://sync.test/",
        session_token="sess",
        gitea_token="gt",
        gitea_username="u1",
        account={"id": "acct_1", "email": "a@x.io", "display_name": "A"},
    )
    assert credentials.is_logged_in() is True
    assert credentials.get_server_url() == "https://sync.test"  # trailing slash stripped
    assert credentials.get_session_token() == "sess"
    assert credentials.get_gitea_token() == "gt"
    assert credentials.get_gitea_username() == "u1"
    assert credentials.get_account()["email"] == "a@x.io"


def test_clear(fake_keyring: dict) -> None:
    credentials.store_session(
        server_url="s", session_token="x", gitea_token="y", gitea_username="u", account={"id": "z"}
    )
    credentials.clear()
    assert credentials.is_logged_in() is False
    assert credentials.get_account() is None
    assert credentials.get_server_url() is None


def test_update_tokens(fake_keyring: dict) -> None:
    credentials.store_session(
        server_url="s", session_token="x", gitea_token="y", gitea_username="u", account={"id": "z"}
    )
    credentials.update_session_token("x2")
    credentials.update_gitea_token("y2")
    assert credentials.get_session_token() == "x2"
    assert credentials.get_gitea_token() == "y2"
