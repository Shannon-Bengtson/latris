"""Named report pack configurations — section filter sets for different audiences."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackConfig:
    """Which sections to include in a report for a given audience."""

    name: str
    sections: list[str] = field(default_factory=list)
    audience: str = ""
    purpose: str = ""


# Section names match the heading keys used in markdown.py and word.py
ALL_SECTIONS = [
    "foundation",
    "structure",
    "history",
    "diagram",
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
        audience="people outside the modelling work — a client, board or funder",
        purpose=(
            "answer first: the interpretation, the diagram, findings, then each link with its reasoning and "
            "evidence, and sources — without internal IDs or the change log"
        ),
        # Order is the reading order: a board reads the answer before the tables.
        sections=["foundation", "interpretation", "diagram", "structure", "findings", "edges", "nodes", "evidence", "assumptions", "exclusions", "decisions", "modelling_approach", "references"],  # noqa: E501
    ),
    "audit": PackConfig(
        name="audit",
        audience="an auditor or the modelling team",
        purpose="the complete record — every section, including decisions, sign-offs, sessions and data",
        sections=ALL_SECTIONS,  # everything
    ),
    "review": PackConfig(
        name="review",
        audience="a reviewer checking the model",
        purpose="the model with its evidence, open challenges and questions, and findings",
        sections=["foundation", "structure", "history", "diagram", "modelling_approach", "nodes", "edges", "evidence", "challenges", "questions", "findings", "interpretation"],  # noqa: E501
    ),
    "workshop": PackConfig(
        name="workshop",
        audience="a working session with stakeholders",
        purpose="structure, assumptions, open questions and session notes",
        sections=["foundation", "structure", "history", "diagram", "nodes", "edges", "assumptions", "questions", "sessions"],  # noqa: E501
    ),
    "publication": PackConfig(
        name="publication",
        audience="a paper or public write-up",
        purpose="the model, evidence, findings, interpretation and full references, without internal IDs",
        sections=["foundation", "interpretation", "diagram", "structure", "findings", "modelling_approach", "edges", "nodes", "evidence", "references"],  # noqa: E501
    ),
}


def get_pack(name: str) -> PackConfig:
    """Look up a pack config by name. Raises KeyError if unknown."""
    if name not in PACKS:
        known = ", ".join(sorted(PACKS))
        raise KeyError(f"Unknown pack {name!r}. Known packs: {known}")
    return PACKS[name]
