"""Spike: pin the pgmpy 1.x API surface used by the BN inference adapter.

This is a deliberately self-contained probe (no latris imports). It
documents the exact pgmpy classes, the ``TabularCPD`` column convention, and
the ``VariableElimination`` result shape that ``operations/_bn_engine.py`` will
target in chunk 3. If a future pgmpy bump moves the API, this test fails first
and in isolation — before any of our own code does.

pgmpy went 0.x -> 1.x: the network class is now ``DiscreteBayesianNetwork``
(``BayesianModel``/``BayesianNetwork`` are gone), which is precisely the kind
of drift this spike exists to catch.
"""

from __future__ import annotations

import pytest

pgmpy = pytest.importorskip("pgmpy")

from pgmpy.factors.discrete import TabularCPD  # noqa: E402
from pgmpy.inference import VariableElimination  # noqa: E402
from pgmpy.models import DiscreteBayesianNetwork  # noqa: E402


def _rain_wet_model() -> DiscreteBayesianNetwork:
    """Two-node sprinkler-style network with a hand-verifiable posterior.

    P(rain=yes) = 0.2
    P(wet=yes | rain=yes) = 0.9 ; P(wet=yes | rain=no) = 0.1
    """
    model = DiscreteBayesianNetwork([("rain", "wet")])

    cpd_rain = TabularCPD(
        "rain", 2, [[0.2], [0.8]],
        state_names={"rain": ["yes", "no"]},
    )
    # TabularCPD `values`: rows = this variable's states (here wet: yes, no),
    # columns = the cartesian product of evidence states, in `evidence` order.
    cpd_wet = TabularCPD(
        "wet", 2,
        [[0.9, 0.1],   # wet=yes | rain=yes, rain=no
         [0.1, 0.9]],  # wet=no  | rain=yes, rain=no
        evidence=["rain"], evidence_card=[2],
        state_names={"wet": ["yes", "no"], "rain": ["yes", "no"]},
    )
    model.add_cpds(cpd_rain, cpd_wet)
    return model


def test_model_validates() -> None:
    model = _rain_wet_model()
    assert model.check_model() is True


def test_prior_marginal() -> None:
    infer = VariableElimination(_rain_wet_model())
    res = infer.query(variables=["wet"], show_progress=False)
    # P(wet=yes) = 0.9*0.2 + 0.1*0.8 = 0.26
    idx = res.state_names["wet"].index("yes")
    assert res.values[idx] == pytest.approx(0.26)


def test_posterior_given_evidence() -> None:
    infer = VariableElimination(_rain_wet_model())
    res = infer.query(variables=["rain"], evidence={"wet": "yes"}, show_progress=False)

    # Result is a DiscreteFactor exposing .variables / .state_names / .values —
    # the exact surface the adapter maps back into our plain dict result.
    assert type(res).__name__ == "DiscreteFactor"
    assert res.variables == ["rain"]
    assert res.state_names == {"rain": ["yes", "no"]}

    # Bayes: P(rain=yes | wet=yes) = 0.9*0.2 / (0.9*0.2 + 0.1*0.8) = 0.6923...
    idx = res.state_names["rain"].index("yes")
    assert res.values[idx] == pytest.approx(0.6923076923, abs=1e-9)
