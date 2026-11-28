"""a_or_an: the indefinite article for generated messages."""

from __future__ import annotations

import pytest

from latris.operations._words import a_or_an


@pytest.mark.parametrize(("phrase", "expected"), [
    ("end state", "an end state"),
    ("evidence item", "an evidence item"),
    ("escalation factor", "an escalation factor"),
    ("informational link", "an informational link"),
    ("option", "an option"),
    ("criterion", "a criterion"),
    ("barrier", "a barrier"),
    ("uniform distribution", "a uniform distribution"),
    ("unknown", "an unknown"),
    ("hour", "an hour"),
    ("'edge' ID", "an 'edge' ID"),
    ("'node' ID", "a 'node' ID"),
    ("SD role", "an SD role"),
    ("DAG role", "a DAG role"),
    ("Event Tree role", "an Event Tree role"),
    ("", "a "),
])
def test_a_or_an(phrase: str, expected: str) -> None:
    assert a_or_an(phrase) == expected
