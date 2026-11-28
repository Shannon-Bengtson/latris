"""Equation text must never reach ``exec``/``eval`` in the SD fast path unless it is whitelisted.

``_sd_fast`` compiles equations into Python source and runs it. Two layers stand in the way of
malicious equation text: ``_sd_eval.parse`` (every equation a model is built from), and the fast
compiler's own re-check of every node before it generates code. Both are tested here, the second
with the first bypassed (an equation swapped into an already-built model), with ``exec`` and
``eval`` spied on so a case that reached them would show.
"""

from __future__ import annotations

import pytest

from latris.operations import _sd_fast
from latris.operations._sd_eval import FUNCTIONS, EquationError, ParsedEquation, parse, slugify
from latris.operations.sd_inference import build_model
from tests.operations.test_sd_inference import M, bathtub

pytest.importorskip("scipy")

MALICIOUS = [
    # imports and builtins
    "__import__('os').system('echo pwned')",
    "__import__('os')",
    "eval('1')",
    "exec('import os')",
    "open('/etc/passwd')",
    "getattr(water, '__class__')",
    "globals()",
    "vars()",
    "compile('1', 'x', 'eval')",
    "print(water)",
    "min(water, 1)",  # a helper the generated code uses, but not an equation function
    "_pow(water, 2)",
    # attribute access and dunders
    "().__class__",
    "().__class__.__bases__[0].__subclasses__()",
    "water.__class__",
    "water.real",
    "water.conjugate()",
    "MIN.__globals__",
    "__builtins__",
    "__builtins__['eval']('1')",
    "__class__",
    # lambdas and comprehension tricks
    "lambda: 0",
    "(lambda x: x)(water)",
    "[x for x in (1, 2)]",
    "(x for x in (1, 2))",
    "{x for x in (1, 2)}",
    "{x: 1 for x in (1, 2)}",
    "[c for c in ().__class__.__mro__]",
    "MIN([water][0], 1)",
    # other syntax outside the whitelist
    "water[0]",
    "(w := 1)",
    "MIN(*water)",
    "MIN(water, key=print)",
    "MAX(water, 1, default=__import__('os'))",
    # well-formed apart from the keyword: the compiler used to drop it silently and generate code
    "MAX(water * drain_rate, water * drain_rate, key=__import__)",
    "ABS(water * drain_rate, k=().__class__)",
    "water * drain_rate * EXP(0, x=lambda: 0)",
    "'a string'",
    "b'bytes'",
    "f'{water}'",
    "1 if water else 2",
    "~1",
    "1 // 2",
    "1 % 2",
    "1 << 2",
    "water @ water",
    "(1, 2)",
    "{1}",
    "...",
    "1j",
    "None",
]


@pytest.mark.parametrize("text", MALICIOUS)
def test_parse_refuses_malicious_equations(text: str) -> None:
    # The dunder-name cases parse as plain names; they're refused as unknown variables, and a
    # variable can never be named that way (see the slug test below). Everything else is refused here.
    if text in ("__builtins__", "__class__"):
        assert parse(text).names == {text}
        return
    with pytest.raises(EquationError):
        parse(text)


@pytest.mark.parametrize("label", ["__class__", "__builtins__", "__import__", "_pow", "  __x__  "])
def test_no_variable_slug_is_a_dunder_or_private_name(label: str) -> None:
    assert not slugify(label).startswith("_") or slugify(label)[1].isdigit()


def test_building_a_model_with_a_malicious_equation_fails() -> None:
    bad = M()
    w = bad.stock("Water", 1.0, "liter")
    bad.flow("Outflow", "__import__('os').system('echo pwned')", "liter/year", frm=w, inputs=[])
    with pytest.raises(EquationError):
        build_model(*bad.args(final_time=1, dt=1))


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every source string the fast path would exec or eval."""
    seen: list[str] = []

    def spy_exec(code, ns):
        seen.append("exec")
        return exec(code, ns)  # noqa: S102 - the real exec, only reached by a whitelisted model

    def spy_eval(code, ns):
        seen.append("eval")
        return eval(code, ns)  # noqa: S307

    monkeypatch.setattr(_sd_fast, "exec", spy_exec, raising=False)
    monkeypatch.setattr(_sd_fast, "eval", spy_eval, raising=False)
    return seen


def _model_with(text: str):
    model = build_model(*bathtub().args(final_time=2, dt=1))
    target = next(v for v in model.order if "water" in model.equations[v].expression)
    model.equations[target] = ParsedEquation(expression=text, node=None, names=frozenset(), uses_table=False)
    return model


def test_a_whitelisted_model_does_compile(spies: list[str]) -> None:
    assert _sd_fast.compile_model(build_model(*bathtub().args(final_time=2, dt=1))) is not None
    assert "exec" in spies and "eval" in spies


@pytest.mark.parametrize("text", MALICIOUS)
def test_fast_compiler_refuses_before_generating_code(text: str, spies: list[str]) -> None:
    assert _sd_fast.compile_model(_model_with(text)) is None
    assert spies == []


def test_every_call_name_in_the_whitelist_is_an_equation_function() -> None:
    # The generated code calls helpers by fixed names; none of them is reachable from equation text.
    assert not set(_sd_fast._HELPERS) & set(FUNCTIONS)


def test_generated_source_names_only_its_own_variables_and_helpers() -> None:
    import ast
    import re

    m = M()
    p = m.stock("Population", 100.0, "person")
    cap = m.const("Cap", 30.0, "person/year")
    rate = m.const("Rate", 0.2, "1/year")
    m.flow("Births", "MAX(0, MIN(cap, population * rate)) + STEP(cap, 2) * SIN(PI * 0)", "person/year",
           to=p, inputs=[p, cap, rate])
    fast = _sd_fast.compile_model(build_model(*m.args(final_time=3, dt=1)))
    assert fast is not None
    names = {n.id for n in ast.walk(ast.parse(fast.source)) if isinstance(n, ast.Name)}
    own = {n for n in names if re.fullmatch(r"[svc]\d+|_t|t|y|c|TF", n)}
    assert names - own <= set(_sd_fast._HELPERS)
    assert not any(isinstance(n, ast.Attribute | ast.Lambda | ast.Import) for n in ast.walk(ast.parse(fast.source)))
