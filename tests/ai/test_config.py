from __future__ import annotations

from pathlib import Path

import pytest

from latris.ai import config as ai_config
from latris.operations.init import init_project
from latris.repo.layout import ProjectPaths


@pytest.fixture
def project(tmp_path: Path, git_identity):
    root = tmp_path / "demo"
    init_project(root, statement="Q?")
    return ProjectPaths(root)


def test_load_returns_defaults_when_file_absent(project: ProjectPaths) -> None:
    cfg = ai_config.load(project)
    assert cfg.default_model == ai_config.DEFAULT_MODEL
    assert cfg.temperature == ai_config.DEFAULT_TEMPERATURE
    assert cfg.max_tokens == ai_config.DEFAULT_MAX_TOKENS


def test_save_then_load_roundtrips(project: ProjectPaths) -> None:
    original = ai_config.AIConfig(
        default_model="gpt-5",
        temperature=0.7,
        max_tokens=4096,
    )
    ai_config.save(project, original)
    loaded = ai_config.load(project)
    assert loaded == original


def test_save_writes_into_state_dir(project: ProjectPaths) -> None:
    cfg = ai_config.AIConfig()
    path = ai_config.save(project, cfg)
    assert path == project.state_dir / "ai_config.yaml"
    assert path.is_file()


def test_config_forbids_extra_keys() -> None:
    # Extra keys are forbidden so a typo doesn't silently ignore a setting.
    with pytest.raises(Exception, match="extra"):
        ai_config.AIConfig.model_validate({"default_model": "x", "unknown": 1})


def test_config_rejects_secret_looking_model() -> None:
    with pytest.raises(ValueError, match="secret"):
        ai_config.AIConfig(default_model="sk-live-abc_api_key")


def test_temperature_out_of_range() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ai_config.AIConfig(temperature=3.0)


def test_max_tokens_must_be_positive() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ai_config.AIConfig(max_tokens=0)


def test_resolve_model_precedence(
    project: ProjectPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # project config
    ai_config.save(project, ai_config.AIConfig(default_model="from-config"))
    assert ai_config.resolve_model(project) == "from-config"

    # env beats config
    monkeypatch.setenv(ai_config.MODEL_ENV_VAR, "from-env")
    assert ai_config.resolve_model(project) == "from-env"

    # override beats env
    assert ai_config.resolve_model(project, override="from-flag") == "from-flag"


def test_resolve_model_falls_back_to_hardcoded_default(
    project: ProjectPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ai_config.MODEL_ENV_VAR, raising=False)
    # no file saved
    assert ai_config.resolve_model(project) == ai_config.DEFAULT_MODEL


def test_resolve_temperature_forces_provider_override() -> None:
    # Moonshot rejects free temperatures (400 at call time) — the forced
    # value depends on thinking mode: 1.0 with thinking enabled, 0.6 with
    # the thinking-disabled extra_body Latris sends.
    assert ai_config.resolve_temperature("moonshot/kimi-k2.6", 0.3) == 0.6
    assert ai_config.resolve_temperature("moonshot/kimi-k2.7-code", 0.0) == 0.6


def test_resolve_temperature_passes_through_unlisted_providers() -> None:
    # Per-prompt and per-config temperatures survive for normal providers.
    assert ai_config.resolve_temperature("gemini/gemini-2.5-flash", 0.3) == 0.3
    assert ai_config.resolve_temperature("anthropic/claude-sonnet-4-6", 0.0) == 0.0
    assert ai_config.resolve_temperature("gpt-5", 0.7) == 0.7


def test_resolve_extra_body_for_thinking_prone_providers() -> None:
    # Moonshot thinking models blow the token budget on large structured
    # prompts; the adapter must send thinking-disabled via extra_body.
    assert ai_config.resolve_extra_body("moonshot/kimi-k2.6") == {
        "thinking": {"type": "disabled"}
    }


def test_resolve_extra_body_empty_for_normal_providers() -> None:
    assert ai_config.resolve_extra_body("gemini/gemini-2.5-flash") == {}
    assert ai_config.resolve_extra_body("anthropic/claude-sonnet-4-6") == {}
