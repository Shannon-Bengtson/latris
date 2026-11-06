"""Tests for the ``latris.server_plugins`` entry-point hook."""

from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from latris.server import app as app_module

_router = APIRouter()


@_router.get("/api/plugin-ping")
def _ping() -> dict[str, str]:
    return {"pong": "yes"}


def register(app: FastAPI) -> None:
    app.include_router(_router)


def _fake_entry_points(*names: str):
    eps = [EntryPoint(name=n, value=f"{__name__}:register", group=app_module.PLUGIN_ENTRY_POINT_GROUP) for n in names]

    def entry_points(*, group: str):
        return eps if group == app_module.PLUGIN_ENTRY_POINT_GROUP else []

    return entry_points


def test_plugin_routes_are_registered(monkeypatch) -> None:
    monkeypatch.setattr("importlib.metadata.entry_points", _fake_entry_points("demo"))
    client = TestClient(app_module.create_app())
    assert client.get("/api/plugin-ping").json() == {"pong": "yes"}


def test_no_plugins_is_fine() -> None:
    client = TestClient(app_module.create_app())
    assert client.get("/api/plugin-ping").status_code == 404


def test_broken_plugin_refuses_to_start(monkeypatch) -> None:
    bad = [EntryPoint(name="bad", value="latris_no_such_module:register", group=app_module.PLUGIN_ENTRY_POINT_GROUP)]
    monkeypatch.setattr("importlib.metadata.entry_points", lambda *, group: bad)
    with pytest.raises(ModuleNotFoundError):
        app_module.create_app()


def test_plugins_named_in_env_var(monkeypatch) -> None:
    monkeypatch.setattr("importlib.metadata.entry_points", lambda *, group: [])
    monkeypatch.setenv("LATRIS_SERVER_PLUGINS", f" {__name__}:register , ")
    client = TestClient(app_module.create_app())
    assert client.get("/api/plugin-ping").json() == {"pong": "yes"}


_calls: list[FastAPI] = []


def register_counting(app: FastAPI) -> None:
    _calls.append(app)


def test_env_var_and_entry_point_register_once(monkeypatch) -> None:
    ep = EntryPoint(name="demo", value=f"{__name__}:register_counting", group=app_module.PLUGIN_ENTRY_POINT_GROUP)
    monkeypatch.setattr("importlib.metadata.entry_points", lambda *, group: [ep])
    monkeypatch.setenv("LATRIS_SERVER_PLUGINS", f"{__name__}:register_counting")
    _calls.clear()
    app_module.create_app()
    assert len(_calls) == 1
