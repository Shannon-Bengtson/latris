"""PersonInput: an answer needs the answers, a skip needs a reason."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from latris.schema import CHECKPOINT_ORDER, HumanActor, PersonInput, PersonInputLog, new_id

ME = HumanActor(name="Pat", email="pat@example.com")


def test_answered_needs_answers() -> None:
    with pytest.raises(ValidationError, match="needs the person's answers"):
        PersonInput(id=new_id("person-input"), checkpoint="framing", outcome="answered", answers="  ",
                    authored_by=ME)


def test_skipped_needs_reason() -> None:
    with pytest.raises(ValidationError, match="needs a reason"):
        PersonInput(id=new_id("person-input"), checkpoint="framing", outcome="skipped", authored_by=ME)


def test_unknown_checkpoint_refused() -> None:
    with pytest.raises(ValidationError):
        PersonInput(id=new_id("person-input"), checkpoint="vibes", outcome="answered", answers="x",  # type: ignore[arg-type]
                    authored_by=ME)


def test_defaults() -> None:
    log = PersonInputLog()
    assert log.pace == "ask" and log.entries == []
    assert CHECKPOINT_ORDER == ("framing", "structure", "values", "surprise", "audience")
