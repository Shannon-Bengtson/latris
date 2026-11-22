"""Test commits are never signed (tests/conftest.py ``_no_commit_signing``)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_commits_skip_signing_even_where_git_config_asks_for_it(tmp_path: Path, git_identity) -> None:
    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=False)

    git("init", "-q")
    # As a machine's global config might: sign every commit, with a signer that always fails.
    git("config", "commit.gpgsign", "true")
    git("config", "gpg.format", "openpgp")
    git("config", "gpg.program", "false")
    result = git("commit", "--allow-empty", "-q", "-m", "x")
    assert result.returncode == 0, result.stderr
