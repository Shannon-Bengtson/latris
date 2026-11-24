"""Guard: the type annotations are checked, and no file gets more type errors.

``mypy`` checks ``src/latris`` with the settings in ``pyproject.toml`` (``[tool.mypy]``). The package
arrived at this guard with type errors — nearly all from loosely typed dicts and optional values that
are checked some other way, not bugs — so each file's count when the guard arrived is listed in
``type_errors.txt``. The list only shrinks: a file not listed must have none, a listed file must not
gain any, and a file whose errors are fixed must have its count lowered (or come off the list). The
mypy version is pinned in the ``dev`` extra, because another release finds a different set. See
docs/engineering/TESTING.md.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = Path(__file__).with_name("type_errors.txt")
_ERROR = re.compile(r"^(?P<path>[^:]+\.py):\d+: error: ")


def _counts(monkeypatch: pytest.MonkeyPatch) -> tuple[Counter[str], str]:
    api = pytest.importorskip("mypy.api", reason="mypy comes with the dev extra")
    # From the repo root, mypy names files relative to it ("src/latris/…", with "\\" on Windows).
    monkeypatch.chdir(ROOT)
    out, err, status = api.run(["--config-file", "pyproject.toml", "--no-error-summary", "--show-error-codes"])
    if status not in (0, 1):  # 1: type errors found; anything else: mypy itself failed
        pytest.fail(f"mypy didn't run:\n{err or out}")
    out = out.replace("\\", "/")
    counts: Counter[str] = Counter(m["path"] for m in map(_ERROR.match, out.splitlines()) if m)
    return counts, out


def _allowed() -> dict[str, int]:
    rows = (ln.split() for ln in ALLOWED.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#"))
    return {path: int(n) for path, n in rows}


def test_no_file_gets_more_type_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    counts, out = _counts(monkeypatch)
    allowed = _allowed()
    new = sorted(f"{path} {n}" for path, n in counts.items() if n > allowed.get(path, 0))
    if new:
        errors = "\n".join(ln for ln in out.splitlines() if _ERROR.match(ln) and ln.split(":")[0] in {
            row.split()[0] for row in new})
        pytest.fail(f"type errors added (file, errors now) — fix them:\n{chr(10).join(new)}\n\n{errors}")
    fewer = sorted(f"{path} {counts.get(path, 0)} (listed at {n})" for path, n in allowed.items() if counts.get(path, 0) < n)
    assert fewer == [], f"fewer type errors now: lower these in {ALLOWED.name} (or take a file at 0 off)"
