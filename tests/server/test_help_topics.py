"""The help topics' files (``server/help_topics/``) and the loader that reads them."""

from __future__ import annotations

from pathlib import Path

import pytest

from latris.server.help import HELP_CATEGORIES, HELP_TOPICS, _load_topics, _parse_topic

TOPIC = "---\ntitle: Tides\ncategory: build\nsummary: Why the sea moves: the short version.\nplace: build.structure\n---\n\n## Tides\n\nText.\n"


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
        (TOPIC.replace("place: build.structure", "place: build.tides"), "not a workflow place"),
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


# ---------- model-type topics are headed by workflow step (schema/workflow.py, latris#62) ----------

_TOPIC_TYPE = {
    "bn": "bn", "sd": "sd", "cld": "cld", "dag": "dag", "fcm": "fcm", "toc": "theory_of_change",
    "ft": "fault_tree", "bowtie": "bow_tie", "et": "event_tree", "mcda": "mcda", "ach": "ach",
    "dt": "decision_tree", "markov": "markov", "argument-map": "argument_map", "equation-model": "equation_model",
}


def _analyse_headings(body: str) -> list[str]:
    """The step ids of the ``## `` headings that name an Analyse step (optionally followed by " (method)")."""
    from latris.schema import workflow as wf

    names = {wf.step(s).name: s for s in wf.step_ids("analyse")}
    out = []
    for line in body.splitlines():
        if line.startswith("## "):
            title = line[3:].split(" (", 1)[0]
            if title in names:
                out.append(names[title])
    return out


@pytest.mark.parametrize("suffix", sorted(_TOPIC_TYPE))
def test_model_type_topics_are_headed_by_analyse_step(suffix: str) -> None:
    from latris.operations import formalisms
    from latris.schema import workflow as wf

    topic = next(t for t in HELP_TOPICS if t.id == f"model-type-{suffix}")
    headings = _analyse_headings(topic.body)
    order = list(wf.step_ids("analyse"))
    assert headings == sorted(headings, key=order.index), "analyse headings out of the registry's order"
    assert len(headings) == len(set(headings)), "an analyse step headed twice"
    recorded = {r.step for r in formalisms.results_of(_TOPIC_TYPE[suffix])}
    assert recorded <= set(headings), f"no heading for {sorted(recorded - set(headings))}"
    for old in ("What the analysis shows", "What the analyses show", "Analysis outputs", "How sure is"):
        assert f"## {old}" not in topic.body
