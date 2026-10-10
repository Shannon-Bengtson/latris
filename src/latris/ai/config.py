"""AI config — per-project defaults for LLM calls.

Lives at ``<project>/.graph-tooling/ai_config.yaml`` and is **committed**
so teammates use the same model by default. API keys do NOT live here;
keys are keyring- or env-var-only (see ``credentials.py``).

Per-call overrides beat this; this beats the hardcoded default.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model

CONFIG_FILENAME = "ai_config.yaml"

DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 16384
MODEL_ENV_VAR = "LATRIS_AI_MODEL"

_FORBIDDEN_SUBSTRINGS = ("api_key", "apikey", "secret", "token", "password")


class AIConfig(BaseModel):
    """Project-level AI defaults."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    default_model: str = DEFAULT_MODEL
    temperature: float = Field(DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    max_tokens: int = Field(DEFAULT_MAX_TOKENS, gt=0)
    # AI interrogation Phase 2c. When True, generating Interpret*
    # prose is rejected if the CompletenessGate report contains any
    # `severity=required` entry with `status=open`. Default False —
    # the gate runs in non-blocking warning mode until calibrated.
    completeness_gate_blocking: bool = False

    @field_validator("default_model")
    @classmethod
    def _guard_against_secret_leak(cls, v: str) -> str:
        lowered = v.lower()
        if any(tok in lowered for tok in _FORBIDDEN_SUBSTRINGS):
            raise ValueError(
                "default_model looks like a secret; API keys do not belong in "
                "ai_config.yaml. Use `latris ai key set <provider>` "
                "or an env var."
            )
        return v


def config_path(paths: ProjectPaths) -> Path:
    return paths.state_dir / CONFIG_FILENAME


def load(paths: ProjectPaths) -> AIConfig:
    """Load config for a project, returning defaults if the file doesn't exist."""
    p = config_path(paths)
    if not p.exists():
        return AIConfig()
    return load_model(AIConfig, p)


def save(paths: ProjectPaths, config: AIConfig) -> Path:
    p = config_path(paths)
    dump_model(config, p)
    return p


def resolve_model(
    paths: ProjectPaths,
    override: str | None = None,
) -> str:
    """Resolve the effective model name.

    Precedence: ``override`` (e.g. ``--model`` flag) > env var
    (``LATRIS_AI_MODEL``) > project config > hardcoded default.
    """
    if override:
        return override
    env_override = os.environ.get(MODEL_ENV_VAR)
    if env_override:
        return env_override
    return load(paths).default_model


# Providers whose current APIs reject free sampling params. Moonshot fixes
# temperature per model/mode: thinking-enabled models only accept 1.0;
# with thinking disabled (our extra_body) kimi-k2.6 only accepts 0.6. Since
# Latris disables thinking for moonshot, the forced value is 0.6. Provider
# prefix -> forced temperature, applied after per-prompt and project-config
# resolution so those models never 400 at call time.
PROVIDER_TEMPERATURE_OVERRIDES: dict[str, float] = {
    "moonshot": 0.6,
}


def resolve_temperature(model: str, temperature: float) -> float:
    """Apply provider-mandated sampling params for ``model``.

    Per-provider overrides win over per-prompt and project-config values.
    Models not listed pass the requested temperature through unchanged.
    """
    provider = model.split("/", 1)[0].lower() if "/" in model else ""
    return PROVIDER_TEMPERATURE_OVERRIDES.get(provider, temperature)


# Provider-specific extra request-body params. Moonshot's thinking models
# burn unbounded reasoning tokens on large structured prompts (observed:
# 47.5k reasoning tokens on DraftConceptualModel before max_tokens cut the
# output). Thinking-disabled keeps them inside the budget and parsing
# reliably; the API accepts it (verified 2026-10).
PROVIDER_EXTRA_BODY: dict[str, dict[str, Any]] = {
    "moonshot": {"thinking": {"type": "disabled"}},
}


def resolve_extra_body(model: str) -> dict[str, Any]:
    """Provider-specific extra request params for ``model`` ({} if none)."""
    provider = model.split("/", 1)[0].lower() if "/" in model else ""
    return PROVIDER_EXTRA_BODY.get(provider, {})
