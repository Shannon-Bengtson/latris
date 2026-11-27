"""Static in-app help topics.

Help topics are bundled with the application. They are deliberately project
independent: the GUI can open help from any workspace state without needing
to inspect the active project.

The text lives beside this module in ``help_topics/``: one Markdown file per
topic, named for the topic's id, opening with a header that gives its title,
category, one-line summary and place in the workflow::

    ---
    title: Welcome to Latris
    category: getting-started
    summary: What Latris is, what it is for, and the ideas behind it.
    place: project
    ---

``place`` is where the topic's subject sits in the workflow structure (``schema/workflow.py``): a step, a
stage, a track or ``composite``, by the rules in ``docs/engineering/WORKFLOW_STRUCTURE.md``. A model-type
topic is placed at model type selection, where people read what each type is for. ``category`` is the older
grouping the app still reads; it goes once the app groups by place.

    ## What Latris is
    ...

``help_topics/_order.txt`` lists the topic ids in the order they are served.
To add a topic, write its file and add its id to that list.
"""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable

from pydantic import BaseModel

from latris.schema.workflow import is_place


class HelpTopic(BaseModel):
    id: str
    title: str
    category: str
    summary: str
    place: str
    body: str


HELP_CATEGORIES: list[str] = [
    "getting-started",
    "workflow",
    "build",
    "formalise",
    "analyse",
    "interpret",
    "communicate",
    "collaboration",
    "model-types",
    "evidence",
    "provenance",
    "ai",
    "versioning",
    "developer",
]

_HEADER_KEYS = ("title", "category", "summary", "place")


def _parse_topic(topic_id: str, text: str) -> HelpTopic:
    """A topic from its file: a ``---`` header of ``key: value`` lines, a blank line, then the body."""
    opening, _, rest = text.partition("\n")
    header, closed, body = rest.partition("\n---\n")
    if opening != "---" or not closed:
        raise ValueError(f"help topic {topic_id!r}: the file must open with a '---' header closed by '---'")
    fields = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
    if tuple(fields) != _HEADER_KEYS:
        raise ValueError(f"help topic {topic_id!r}: the header must give {', '.join(_HEADER_KEYS)}, in that order")
    if fields["category"] not in HELP_CATEGORIES:
        raise ValueError(f"help topic {topic_id!r}: no category {fields['category']!r}")
    if not is_place(fields["place"]):
        raise ValueError(f"help topic {topic_id!r}: {fields['place']!r} is not a workflow place")
    return HelpTopic(id=topic_id, body=body.removeprefix("\n"), **fields)


def _load_topics(folder: Traversable) -> list[HelpTopic]:
    """Every topic in *folder*, in the order its ``_order.txt`` gives."""
    lines = (folder / "_order.txt").read_text(encoding="utf-8").splitlines()
    order = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    files = {p.name.removesuffix(".md") for p in folder.iterdir() if p.name.endswith(".md")}
    if len(set(order)) != len(order) or set(order) != files:
        unlisted, missing = sorted(files - set(order)), sorted(set(order) - files)
        raise ValueError(
            f"help_topics/_order.txt must list each topic file once: not listed {unlisted}, no file for {missing}"
        )
    return [_parse_topic(i, (folder / f"{i}.md").read_text(encoding="utf-8")) for i in order]


HELP_TOPICS: list[HelpTopic] = _load_topics(resources.files(__package__) / "help_topics")


def list_topics() -> list[dict]:
    """Return all topics without body content for the list view."""
    return [t.model_dump(mode="json", exclude={"body"}) for t in HELP_TOPICS]


def get_topic(topic_id: str) -> HelpTopic | None:
    """Return a single topic by ID, or None if not found."""
    for topic in HELP_TOPICS:
        if topic.id == topic_id:
            return topic
    return None
