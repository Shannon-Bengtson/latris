"""Round-trip tests for the unified Maturity ladder + MaturityBadges."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from latris.schema.maturity import MATURITY_ORDER, Maturity, MaturityBadges


def test_maturity_order_is_three_step():
    assert MATURITY_ORDER == ("proposed", "reviewed", "approved")


def test_maturity_badges_default_all_false():
    badges = MaturityBadges()
    assert badges.has_evidence is False
    assert badges.has_challenges is False
    assert badges.has_formalism is False
    assert badges.has_quantification is False
    assert badges.has_confirmed_prediction is False


def test_maturity_badges_round_trip():
    original = MaturityBadges(
        has_evidence=True,
        has_challenges=False,
        has_formalism=True,
        has_quantification=True,
        has_confirmed_prediction=False,
    )
    dumped = original.model_dump()
    rehydrated = MaturityBadges.model_validate(dumped)
    assert rehydrated == original


def test_maturity_badges_rejects_unknown_field():
    with pytest.raises(ValidationError):
        MaturityBadges.model_validate({"has_typo": True})


def test_maturity_literal_accepts_three_values():
    for value in ("proposed", "reviewed", "approved"):
        m: Maturity = value  # type: ignore[assignment]
        assert m in MATURITY_ORDER
