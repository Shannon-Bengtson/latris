"""Guard: every CLI command, server route and help topic declares its place in the workflow structure
(schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md). A new one without a place, or with a
place the registry doesn't have, fails here."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.operations.places import cli_places, declared_place, place_of, route_places
from latris.schema import workflow as wf


@pytest.fixture(scope="module")
def routes(tmp_path_factory: pytest.TempPathFactory) -> list[tuple[str, str, str | None]]:
    from latris.server import app as app_module

    # latris's own routes only: an installed plugin brings routes this repo doesn't declare.
    saved = app_module._register_plugins
    app_module._register_plugins = lambda app: None
    try:
        return route_places(app_module.create_app(project_root=Path(tmp_path_factory.mktemp("proj"))))
    finally:
        app_module._register_plugins = saved


def test_every_cli_command_has_a_place() -> None:
    rows = cli_places()
    assert len(rows) > 250
    assert [cmd for cmd, place in rows if place is None] == []
    assert [(cmd, place) for cmd, place in rows if not wf.is_place(place)] == []


def test_every_route_has_a_place(routes) -> None:
    assert len(routes) > 300
    assert [(m, p) for m, p, place in routes if place is None] == []
    assert [(m, p, place) for m, p, place in routes if not wf.is_place(place)] == []


def test_every_help_topic_has_a_place() -> None:
    from latris.server.help import HELP_TOPICS

    assert all(wf.is_place(t.place) for t in HELP_TOPICS)


@pytest.mark.parametrize(
    ("command", "place"),
    [
        ("build", "composite"),
        ("node add", "build.structure"),
        ("project choose", "frame.model_type"),
        ("sd set-constant", "formalise.values"),
        ("sd set-uncertainty", "formalise.ranges"),
        ("sd set-scenario", "formalise.scenarios"),
        ("dt uncertainty", "formalise.definitions"),  # names which chance nodes share an uncertainty
        ("bn learn", "formalise.values"),  # writes values from data: Formalise, not Analyse
        ("sd loops", "analyse.base_case"),
        ("analyse loops", "analyse.structural"),
        ("dt psa", "analyse.uncertainty"),
        ("mcda analyse", "analyse.options"),
        ("toc impact", "analyse.estimation"),
        ("ft check", "validation"),
        ("finding add", "interpret.findings"),
        ("export dot", "communicate.diagram"),
        ("predict", "use.prediction"),
        ("evidence check", "evidence"),
        ("signoff record", "review"),
        ("version milestone", "versions"),
        ("checkpoint record", "ai"),
        ("sync push", "project"),
    ],
)
def test_rules_applied_to_commands(command: str, place: str) -> None:
    assert dict(cli_places())[command] == place


def test_shared_analyse_routes_take_their_types_step(routes) -> None:
    placed = {p: place for m, p, place in routes if p.endswith("/analyse")}
    assert placed["/api/mcda/analyse"] == "analyse.options"
    assert placed["/api/markov/analyse"] == "analyse.options"
    assert placed["/api/ft/analyse"] == "analyse.base_case"
    assert placed["/api/ach/analyse"] == "analyse.base_case"


def test_cli_and_routes_agree_on_shared_operations(routes) -> None:
    by_route = {(m, p): place for m, p, place in routes}
    cli = dict(cli_places())
    for command, method, path in [
        ("sd monte-carlo", "POST", "/api/sd/monte-carlo"),
        ("bn compare", "POST", "/api/bn/compare"),
        ("eq sweep", "POST", "/api/eq/sweep"),
        ("contract check", "GET", "/api/contract/check"),
        ("export md", "GET", "/api/export/markdown"),
        ("fcm set-weight", "POST", "/api/fcm/weight"),
    ]:
        assert cli[command] == by_route[(method, path)], command


def test_resolution_from_a_module_declaration() -> None:
    import types

    mod = types.ModuleType("fake_cmds")
    mod.PLACE = {"*": "formalise.values", "check": "validation", "odd": "analyse.monte_carlo"}
    import sys

    sys.modules["fake_cmds"] = mod
    try:
        def set_x() -> None: ...
        def check() -> None: ...
        def odd() -> None: ...
        for f in (set_x, check, odd):
            f.__module__ = "fake_cmds"
        assert declared_place(set_x) == "formalise.values"
        assert place_of(check) == "validation"
        with pytest.raises(ValueError, match="not a workflow place"):
            place_of(odd)
        mod.PLACE = "evidence"
        assert place_of(odd) == "evidence"
        del mod.PLACE
        with pytest.raises(ValueError, match="declares no workflow place"):
            place_of(odd)
    finally:
        del sys.modules["fake_cmds"]


def test_cli_reference_index_is_current() -> None:
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("gen_cli_index", root / "scripts" / "gen_cli_index.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    text = gen.DOC.read_text(encoding="utf-8")
    assert gen.render(text) == text, "the CLI reference's index is stale: run python scripts/gen_cli_index.py"


def test_composites_name_what_they_carry_out(routes) -> None:
    from latris.cli import build_cmd
    from latris.operations.places import composite_places
    from latris.server.routes import build as build_routes
    from latris.server.routes import configure

    for func in (build_cmd.build, build_routes.build, configure.apply_attributes):
        assert place_of(func) == wf.COMPOSITE
        carried = composite_places(func)
        assert carried and all(wf.is_place(p) and p != wf.COMPOSITE for p in carried), func.__module__


def test_capabilities_list_commands_with_their_place() -> None:
    from latris.operations.capabilities import build_capability_manifest

    commands = {c["command"]: c["place"] for c in build_capability_manifest()["commands"]}
    assert commands["sd monte-carlo"] == "analyse.uncertainty"
    assert commands == dict(cli_places())


def test_openapi_carries_each_routes_place(tmp_path: Path) -> None:
    from latris.server import app as app_module

    saved = app_module._register_plugins
    app_module._register_plugins = lambda app: None
    try:
        paths = app_module.create_app(project_root=tmp_path).openapi()["paths"]
    finally:
        app_module._register_plugins = saved
    assert paths["/api/sd/monte-carlo"]["post"]["x-latris-place"] == "analyse.uncertainty"
    assert paths["/api/mcda/analyse"]["post"]["x-latris-place"] == "analyse.options"
    missing = [(p, m) for p, ops in paths.items() for m, op in ops.items() if "x-latris-place" not in op]
    assert missing == []
