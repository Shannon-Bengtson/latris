"""Named report pack configurations — section filter sets for different audiences."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackConfig:
    """Which sections to include in a report for a given audience."""

    name: str
    sections: list[str] = field(default_factory=list)


# Section names match the heading keys used in markdown.py and word.py
ALL_SECTIONS = [
    "foundation",
    "modelling_approach",
    "nodes",
    "edges",
    "evidence",
    "assumptions",
    "decisions",
    "signoffs",
    "sessions",
    "questions",
    "exclusions",
    "predictions",
    "challenges",
    "references",
    "elicitations",
    "datasets",
    "data_actions",
    "analyses",
    "findings",
    "interpretation",
    "milestones",
]

PACKS: dict[str, PackConfig] = {
    "client": PackConfig(
        name="client",
        sections=["foundation", "modelling_approach", "nodes", "edges", "evidence", "assumptions", "decisions", "exclusions", "findings", "interpretation"],  # noqa: E501
    ),
    "audit": PackConfig(
        name="audit",
        sections=ALL_SECTIONS,  # everything
    ),
    "review": PackConfig(
        name="review",
        sections=["foundation", "modelling_approach", "nodes", "edges", "evidence", "challenges", "questions", "findings", "interpretation"],  # noqa: E501
    ),
    "workshop": PackConfig(
        name="workshop",
        sections=["foundation", "nodes", "edges", "assumptions", "questions", "sessions"],
    ),
    "publication": PackConfig(
        name="publication",
        sections=["foundation", "modelling_approach", "nodes", "edges", "evidence", "references", "findings", "interpretation"],  # noqa: E501
    ),
}


def get_pack(name: str) -> PackConfig:
    """Look up a pack config by name. Raises KeyError if unknown."""
    if name not in PACKS:
        known = ", ".join(sorted(PACKS))
        raise KeyError(f"Unknown pack {name!r}. Known packs: {known}")
    return PACKS[name]
