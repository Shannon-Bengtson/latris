"""The help topics' files (``server/help_topics/``) and the loader that reads them."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.server.help import HELP_CATEGORIES, HELP_TOPICS, _load_topics, _parse_topic

TOPIC = "---\ntitle: Tides\ncategory: build\nsummary: Why the sea moves: the short version.\n---\n\n## Tides\n\nText.\n"


def test_every_topic_is_complete() -> None:
    assert len({t.id for t in HELP_TOPICS}) == len(HELP_TOPICS) > 50
    for topic in HELP_TOPICS:
        assert topic.title and topic.summary and topic.category in HELP_CATEGORIES, topic.id
        assert topic.body.startswith("#") and topic.body.endswith("\n"), topic.id


def test_a_topic_file_is_a_header_then_the_body() -> None:
    topic = _parse_topic("tides", TOPIC)
    assert (topic.id, topic.title, topic.category) == ("tides", "Tides", "build")
    assert topic.summary == "Why the sea moves: the short version."  # a colon in a value is kept
    assert topic.body == "## Tides\n\nText.\n"
    ruled = _parse_topic("tides", TOPIC + "\n---\n\nMore.\n")  # a rule in the body is the body's
    assert ruled.body == "## Tides\n\nText.\n\n---\n\nMore.\n"


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("## Tides\n\nText.\n", "must open with a '---' header"),
        ("---\ntitle: Tides\ncategory: build\n", "must open with a '---' header"),
        (TOPIC.replace("summary: ", "blurb: "), "must give title, category, summary"),
        (TOPIC.replace("title: Tides\ncategory: build\n", "category: build\ntitle: Tides\n"), "in that order"),
        (TOPIC.replace("category: build", "category: tides"), "no category 'tides'"),
    ],
)
def test_a_malformed_topic_file_is_refused(text: str, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        _parse_topic("tides", text)


def test_topics_load_in_the_listed_order(tmp_path: Path) -> None:
    for name in ("tides", "moon"):
        (tmp_path / f"{name}.md").write_text(TOPIC, encoding="utf-8")
    (tmp_path / "_order.txt").write_text("# a comment\nmoon\n\ntides\n", encoding="utf-8")
    assert [t.id for t in _load_topics(tmp_path)] == ["moon", "tides"]


@pytest.mark.parametrize(
    ("order", "problem"),
    [("tides\n", r"not listed \['moon'\]"), ("tides\nmoon\nsun\n", r"no file for \['sun'\]"), ("tides\nmoon\ntides\n", "once")],
)
def test_the_order_list_and_the_files_must_agree(tmp_path: Path, order: str, problem: str) -> None:
    for name in ("tides", "moon"):
        (tmp_path / f"{name}.md").write_text(TOPIC, encoding="utf-8")
    (tmp_path / "_order.txt").write_text(order, encoding="utf-8")
    with pytest.raises(ValueError, match=problem):
        _load_topics(tmp_path)
