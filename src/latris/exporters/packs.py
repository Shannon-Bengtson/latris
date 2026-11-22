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
    # Reader packs group their sections into parts, in reading order: (part heading, chunks). The part
    # heading is a ``##`` and each section under it drops a level. ``None`` heads the untitled opening
    # (title and context). A chunk is a section name or one of ``PART_CHUNKS``. Empty: no parts — the
    # report follows ``sections`` and every section is a ``##``.
    parts: tuple[tuple[str | None, tuple[str, ...]], ...] = ()


# Pieces of a section a part can place on its own (see ``PackConfig.parts``): the person's own expectation
# (from "foundation"), and the interpretation after its answer, split into what it found and how sure it is.
PART_CHUNKS = ("intuition", "interpretation_analysis", "interpretation_confidence")

SUMMARY, THE_MODEL, ANALYSIS, CONFIDENCE, APPENDIX = (
    "Summary",
    "The model",
    "What the analysis shows",
    "How confident we are",
    "Technical appendix",
)


# Section names match the heading keys used in markdown.py
ALL_SECTIONS = [
    "foundation",
    "structure",
    "history",
    "diagram",
    "results",
    "modelling_approach",
    "methods",
    "nodes",
    "edges",
    "evidence",
    "assumptions",
    "decisions",
    "signoffs",
    "sessions",
    "person_input",
    "questions",
    "exclusions",
    "predictions",
    "challenges",
    "contested",
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
            "answer first: the interpretation, the diagram, results (simulations, uncertainty, queries), "
            "findings, contested links (sources for and against), "
            "then each link with its reasoning and evidence, and sources — without internal IDs or the change log"
        ),
        # Order is the reading order: a board reads the answer before the tables.
        sections=["foundation", "interpretation", "diagram", "results", "structure", "findings", "contested", "edges", "nodes", "evidence", "assumptions", "exclusions", "decisions", "modelling_approach", "methods", "person_input", "references"],  # noqa: E501
        # The answer and what it rests on first; the tables and the record last.
        parts=(
            (None, ("foundation",)),
            (SUMMARY, ("interpretation", "intuition", "structure", "findings")),
            (THE_MODEL, ("diagram",)),
            (ANALYSIS, ("results", "interpretation_analysis")),
            (CONFIDENCE, ("interpretation_confidence", "contested", "person_input", "assumptions", "exclusions")),
            (APPENDIX, ("edges", "nodes", "evidence", "decisions", "modelling_approach", "methods", "references")),
        ),
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
        sections=["foundation", "structure", "history", "diagram", "results", "modelling_approach", "methods", "person_input", "nodes", "edges", "contested", "evidence", "challenges", "questions", "findings", "interpretation"],  # noqa: E501
    ),
    "workshop": PackConfig(
        name="workshop",
        audience="a working session with stakeholders",
        purpose="structure, assumptions, open questions and session notes",
        sections=["foundation", "structure", "history", "diagram", "nodes", "edges", "assumptions", "questions", "sessions", "person_input"],  # noqa: E501
    ),
    "publication": PackConfig(
        name="publication",
        audience="a paper or public write-up",
        purpose="the model, evidence, findings, interpretation and full references, without internal IDs",
        sections=["foundation", "interpretation", "diagram", "results", "structure", "findings", "contested", "modelling_approach", "methods", "person_input", "edges", "nodes", "evidence", "references"],  # noqa: E501
        parts=(
            (None, ("foundation",)),
            (SUMMARY, ("interpretation", "intuition", "structure", "findings")),
            (THE_MODEL, ("diagram",)),
            (ANALYSIS, ("results", "interpretation_analysis")),
            (CONFIDENCE, ("interpretation_confidence", "contested", "person_input")),
            (APPENDIX, ("modelling_approach", "methods", "edges", "nodes", "evidence", "references")),
        ),
    ),
}


def get_pack(name: str) -> PackConfig:
    """Look up a pack config by name. Raises KeyError if unknown."""
    if name not in PACKS:
        known = ", ".join(sorted(PACKS))
        raise KeyError(f"Unknown pack {name!r}. Known packs: {known}")
    return PACKS[name]
