"""API-key facade — env vars as the contract, OS keyring as the helper.

The call-site contract: `os.environ["ANTHROPIC_API_KEY"]` (and friends) is
what litellm reads. This module lets users stash keys in the OS keyring
(Windows Credential Manager / macOS Keychain / Linux Secret Service) via
`latris ai key set`, and pull them back into env vars just before
a call.

Design goals:
- **Future-GUI-ready** — the GUI imports ``get_key`` / ``set_key`` /
  ``unset_key`` / ``list_providers`` from here, no CLI duplication.
- **No secrets in git** — keyring only; no project/user config file ever
  holds a key.
- **No secrets in argv** — `ai key set` reads the key via stdin prompt.
- **No secrets in logs** — ``list_providers`` prints provider names and
  never values.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from contextlib import contextmanager

import keyring

SERVICE = "latris"

# The set of providers litellm recognises that map to a standard env var.
# Extend as needed; unknown providers are allowed but won't be env-wired.
PROVIDER_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "azure": "AZURE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "fireworks_ai": "FIREWORKS_AI_API_KEY",
    "together_ai": "TOGETHER_AI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class CredentialError(RuntimeError):
    """Raised when a required credential is missing or unreadable."""


def _env_var_for(provider: str) -> str | None:
    return PROVIDER_ENV.get(provider.lower())


def get_key(provider: str) -> str | None:
    """Resolve the API key for ``provider``.

    Precedence: env var > keyring > ``None``. Callers that strictly need a
    key should use :func:`require_key`.
    """
    env_var = _env_var_for(provider)
    if env_var is not None:
        from_env = os.environ.get(env_var)
        if from_env:
            return from_env
    try:
        return keyring.get_password(SERVICE, provider.lower())
    except Exception:
        return None


def require_key(provider: str) -> str:
    """Like :func:`get_key` but raises ``CredentialError`` if nothing is set."""
    key = get_key(provider)
    if not key:
        env_var = _env_var_for(provider)
        env_hint = f" (or export {env_var}=...)" if env_var else ""
        raise CredentialError(
            f"no API key for provider {provider!r}. Set one with `latris ai key set {provider}`{env_hint}."
        )
    return key


def set_key(provider: str, value: str) -> None:
    if not value:
        raise ValueError("refusing to store empty key value")
    keyring.set_password(SERVICE, provider.lower(), value)


def unset_key(provider: str) -> bool:
    """Remove the key from the keyring. Returns ``True`` if something was removed."""
    try:
        keyring.delete_password(SERVICE, provider.lower())
        return True
    except keyring.errors.PasswordDeleteError:
        return False


def list_providers() -> list[dict[str, str]]:
    """Return providers whose keys are available, with their source. Never values.

    Each entry: ``{"provider": str, "source": "env" | "keyring", "env_var": str | None}``.
    """
    out: list[dict[str, str]] = []
    for provider, env_var in PROVIDER_ENV.items():
        if os.environ.get(env_var):
            out.append({"provider": provider, "source": "env", "env_var": env_var})
            continue
        try:
            if keyring.get_password(SERVICE, provider):
                out.append({"provider": provider, "source": "keyring", "env_var": env_var})
        except Exception:
            continue
    return out


@contextmanager
def key_in_env(providers: Iterable[str]):
    """Context manager — populate env vars from keyring for the duration of a call.

    On entry: for each provider, if its env var is unset but a keyring value
    exists, stage it into ``os.environ``. On exit: remove anything we staged
    (and leave pre-existing env vars untouched). This is how we bridge keyring
    storage → litellm's env-var resolution without leaking secrets into the
    shell environment permanently.
    """
    staged: list[str] = []
    try:
        for provider in providers:
            env_var = _env_var_for(provider)
            if env_var is None:
                continue
            if os.environ.get(env_var):
                continue
            try:
                value = keyring.get_password(SERVICE, provider.lower())
            except Exception:
                value = None
            if value:
                os.environ[env_var] = value
                staged.append(env_var)
        yield
    finally:
        for var in staged:
            os.environ.pop(var, None)
