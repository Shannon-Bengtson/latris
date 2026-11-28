"""A pipe in free text inside a report table is escaped once.

``md.table`` escapes every cell, so a plugin that also runs ``md.esc`` on a cell writes ``\\|``:
the backslash shows and the pipe ends the cell.
"""

from __future__ import annotations

import pytest

from latris.operations import equation_model, risk_uncertainty
from latris.operations.formalisms import _risk_mc
from latris.operations.formalisms import equation_model as em_plugin

_DRIVER = {"input": "Rate", "distribution": "normal", "p5": 1.0, "p95": 2.0, "spearman": 0.5,
           "reason": "survey | 2024", "weak": False, "units": "", "outside_valid": 0}
_ONCE, _TWICE = "survey \\| 2024", "survey \\\\| 2024"


@pytest.fixture
def plain_describe(monkeypatch):
    for mod, name in ((risk_uncertainty, "describe"), (equation_model, "describe"),
                      (equation_model, "describe_monte_carlo")):
        monkeypatch.setattr(mod, name, lambda p: "summary")


def test_risk_monte_carlo_driver_reason(plain_describe):
    p = {"outputs": [], "drivers": [_DRIVER], "primary": "Top event", "fixed": [], "runs": 10,
         "sampling": "lhs", "seed": 1}
    text = "\n".join(_risk_mc._render(p))
    assert _ONCE in text and _TWICE not in text


def test_equation_model_monte_carlo_driver_reason(plain_describe):
    p = {"outputs": [], "drivers": [_DRIVER], "primary": "Load", "fixed": [], "runs": 10, "evaluated": 10,
         "sampling": "lhs", "seed": 1}
    text = "\n".join(em_plugin._render_monte_carlo(p))
    assert _ONCE in text and _TWICE not in text


def test_equation_model_quantity_source(plain_describe):
    q = {"quantity": "Rate", "role": next(iter(em_plugin._ROLE_NAMES)), "units": "", "formula": None,
         "valid_min": None, "valid_max": None, "source": "survey | 2024", "weak": False}
    p = {"arms": [{"name": "Base", "values": {"Rate": 1.0}, "changes": [], "outside": []}], "quantities": [q], "units": {},
         "outputs": []}
    text = "\n".join(em_plugin._render_evaluation(p))
    assert _ONCE in text and _TWICE not in text
