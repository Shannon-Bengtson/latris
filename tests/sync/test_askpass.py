from __future__ import annotations

from latris.sync.askpass import build_credential_env


def test_build_env_sets_credentials() -> None:
    env = build_credential_env("user1", "tok1", base={})
    assert env["LATRIS_GITEA_USER"] == "user1"
    assert env["LATRIS_GITEA_TOKEN"] == "tok1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_injects_credential_config_via_env() -> None:
    env = build_credential_env("user1", "tok1", base={})
    assert env["GIT_CONFIG_COUNT"] == "3"
    # first credential.helper is empty (clears inherited helpers e.g. GCM)
    assert env["GIT_CONFIG_KEY_0"] == "credential.helper"
    assert env["GIT_CONFIG_VALUE_0"] == ""
    # second installs our inline helper
    assert env["GIT_CONFIG_KEY_1"] == "credential.helper"
    assert env["GIT_CONFIG_VALUE_1"].startswith("!f()")
    # interactive prompts disabled
    assert env["GIT_CONFIG_KEY_2"] == "credential.interactive"
    assert env["GIT_CONFIG_VALUE_2"] == "false"


def test_token_not_in_config_values() -> None:
    # the token lives only in the env var, not baked into a config value
    env = build_credential_env("user1", "supersecret", base={})
    for i in range(int(env["GIT_CONFIG_COUNT"])):
        assert "supersecret" not in env[f"GIT_CONFIG_VALUE_{i}"]
