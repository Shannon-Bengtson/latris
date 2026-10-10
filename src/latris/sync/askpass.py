"""Build a git subprocess environment that supplies Gitea credentials.

Rather than a ``GIT_ASKPASS`` script (whose cross-platform execution is
fiddly — git can't reliably exec a ``.cmd``/``.py`` on Windows), we inject
git config purely through environment variables (``GIT_CONFIG_COUNT`` /
``GIT_CONFIG_KEY_n`` / ``GIT_CONFIG_VALUE_n``):

1. clear any inherited credential helper (e.g. Git Credential Manager on
   Windows, which would otherwise pop an interactive login),
2. install an inline shell credential helper that echoes our username/token
   from ``LATRIS_GITEA_USER`` / ``LATRIS_GITEA_TOKEN``,
3. disable interactive prompts.

Git always ships a POSIX ``sh`` (Git for Windows and dugite-native both
bundle one), so the ``!`` shell helper runs on every OS. The token lives only
in an env var — never in the remote URL, git config files, or process args.
"""

from __future__ import annotations

import os

# Inline credential helper. Git invokes it as ``helper get`` and reads
# ``username=``/``password=`` from stdout. Values come from the env at run time.
_HELPER = (
    '!f() { test "$1" = get && '
    'printf "username=%s\\npassword=%s\\n" '
    '"$LATRIS_GITEA_USER" "$LATRIS_GITEA_TOKEN"; }; f'
)


def build_credential_env(
    username: str,
    token: str,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return an env dict for ``git.run_git(..., env=...)`` carrying credentials."""
    env = dict(base if base is not None else os.environ)

    # Order matters: empty value first clears inherited helpers, then ours.
    config_pairs = [
        ("credential.helper", ""),
        ("credential.helper", _HELPER),
        ("credential.interactive", "false"),
    ]
    env["GIT_CONFIG_COUNT"] = str(len(config_pairs))
    for i, (key, value) in enumerate(config_pairs):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value

    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LATRIS_GITEA_USER"] = username
    env["LATRIS_GITEA_TOKEN"] = token
    return env
