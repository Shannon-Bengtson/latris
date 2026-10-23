"""Pin the third-party APIs the SD engine depends on — no latris imports.

If a scipy, pint or simpleeval upgrade changes any of these behaviours, this
file fails first, in isolation, pointing straight at the library change rather
than at a confusing downstream SD failure.
"""

from __future__ import annotations

import ast
import math
import operator

import pint
import pytest
import simpleeval

scipy_integrate = pytest.importorskip("scipy.integrate")


@pytest.mark.parametrize("method", ["RK45", "RK23"])
def test_solve_ivp_call_and_result_shape(method):
    t_eval = [0.0, 1.0, 2.0]
    sol = scipy_integrate.solve_ivp(
        lambda t, y: [-y[0]], (0.0, 2.0), [1.0], method=method, t_eval=t_eval, max_step=0.1, rtol=1e-6, atol=1e-9
    )
    assert sol.success is True
    assert sol.status == 0
    assert isinstance(sol.message, str)
    assert list(sol.t) == t_eval
    assert sol.y.shape == (1, 3)  # y[state][time]
    assert sol.y[0][2] == pytest.approx(math.exp(-2), rel=1e-5)


def test_solve_ivp_propagates_rhs_exceptions():
    class Boom(ValueError):
        pass

    def rhs(t, y):
        raise Boom("bad equation")

    with pytest.raises(Boom):
        scipy_integrate.solve_ivp(rhs, (0.0, 1.0), [1.0], method="RK45")


def test_pint_quantity_arithmetic():
    ureg = pint.UnitRegistry()
    q = ureg.Quantity(3.0, "liter") * ureg.Quantity(0.1, "1/year")
    assert q.units == ureg.parse_units("liter/year")
    with pytest.raises(pint.errors.DimensionalityError):
        ureg.Quantity(1, "liter") + ureg.Quantity(1, "year")
    # Comparing a dimensioned quantity with a non-zero bare number raises; zero is allowed.
    with pytest.raises(ValueError):
        _ = ureg.Quantity(3, "year") > 5
    assert ureg.Quantity(3, "year") > 0


def test_pint_custom_dimension():
    ureg = pint.UnitRegistry()
    ureg.define("person = [population] = people")
    assert ureg.parse_units("people/year") == ureg.parse_units("person/year")


def test_simpleeval_default_mult_breaks_on_pint_so_we_replace_operators():
    """simpleeval's default ``*`` probes ``__len__`` (a string-bomb guard), which pint
    quantities expose and then raise on. latris supplies its own operator table."""
    ureg = pint.UnitRegistry()
    names = {"a": ureg.Quantity(2.0, "liter"), "b": ureg.Quantity(3.0, "1/year")}
    with pytest.raises(TypeError):
        simpleeval.SimpleEval(names=names).eval("a * b")

    s = simpleeval.SimpleEval(names=names, operators={ast.Mult: operator.mul})
    parsed = s.parse("a * b")
    assert s.eval("a * b", previously_parsed=parsed).magnitude == 6.0


def test_simpleeval_rejects_unknowns():
    s = simpleeval.SimpleEval(names={})
    with pytest.raises(simpleeval.NameNotDefined):
        s.eval("x")
    with pytest.raises(simpleeval.FunctionNotDefined):
        s.eval("f(1)")
