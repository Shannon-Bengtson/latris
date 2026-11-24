"""Guard: no function grows past the complexity limit.

Complexity here is cyclomatic complexity — one, plus one for each place the code can branch (``if``,
loop, ``except``, boolean operator, comprehension clause, …), counted the way ``radon cc`` counts it. A
function past ``LIMIT`` is hard to test and to change safely. Functions past it when this guard arrived
are listed in ``complexity_exceptions.txt`` with their score; the list only shrinks — a new function must
stay within the limit, a listed one must not grow, and one brought within the limit must come off the
list. See docs/engineering/TESTING.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "latris"
ALLOWED = Path(__file__).with_name("complexity_exceptions.txt")
LIMIT = 30

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_wildcard(case: ast.match_case) -> bool:
    return isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None and case.guard is None


def _complexity(func: ast.AST) -> int:
    """Cyclomatic complexity of *func*; branches inside nested functions and lambdas count towards it."""
    score = 1
    for node in ast.walk(func):
        if node is func:
            continue
        if isinstance(node, (ast.If, ast.IfExp, ast.Assert)):
            score += 1
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            score += 1 + bool(node.orelse)
        elif isinstance(node, (ast.Try, ast.TryStar)):
            score += len(node.handlers) + bool(node.orelse)
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
        elif isinstance(node, ast.match_case) and not _is_wildcard(node):
            score += 1
    return score


def _scores() -> dict[str, int]:
    """``path::name`` → complexity, for every function and method (not ones nested in a function)."""
    scores: dict[str, int] = {}

    def visit(body: list[ast.stmt], rel: str, prefix: str) -> None:
        for node in body:
            if isinstance(node, _FUNCTIONS):
                key = f"{rel}::{prefix}{node.name}"
                scores[key] = max(scores.get(key, 0), _complexity(node))
            elif isinstance(node, ast.ClassDef):
                visit(node.body, rel, f"{prefix}{node.name}.")

    for path in sorted(SRC.rglob("*.py")):
        visit(ast.parse(path.read_text(encoding="utf-8")).body, path.relative_to(SRC).as_posix(), "")
    return scores


def _allowed() -> dict[str, int]:
    rows = (ln.split() for ln in ALLOWED.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#"))
    return {key: int(score) for key, score in rows}


def test_no_function_grows_past_the_complexity_limit() -> None:
    over = {k: v for k, v in _scores().items() if v > LIMIT}
    allowed = _allowed()
    new = sorted(f"{k} {v}" for k, v in over.items() if k not in allowed)
    assert new == [], f"too complex (limit {LIMIT}): split these into smaller functions"
    grown = sorted(f"{k} {v} (listed at {allowed[k]})" for k, v in over.items() if k in allowed and v > allowed[k])
    assert grown == [], "these listed functions got more complex: split them rather than add to them"
    gone = sorted(k for k in allowed if k not in over)
    assert gone == [], f"within the limit now (or gone): take them off {ALLOWED.name}"


def test_the_counter_counts_branches() -> None:
    func = ast.parse(
        "def f(xs, a, b):\n"
        "    if a and b:\n"  # if +1, and +1
        "        return [x for x in xs if x]\n"  # for +1, if +1
        "    for x in xs:\n"  # +1
        "        try:\n"
        "            x()\n"
        "        except ValueError:\n"  # +1
        "            pass\n"
        "    return a if b else None\n"  # +1
    ).body[0]
    assert _complexity(func) == 8
