"""The README, llms.txt and FOUNDATIONS.md, readable from an installed package.

Agents often work where GitHub and latris.app can't be reached (sandboxes),
so the guide travels with the package: the wheel bundles the files under
``latris/_docs`` (pyproject ``force-include``). From a source checkout they
are read from the repo (README.md and llms.txt at the root; FOUNDATIONS.md
under docs/).
"""

from __future__ import annotations

from pathlib import Path

TOPICS = ("agents", "readme", "llms", "foundations")
_FILES = {"readme": "README.md", "llms": "llms.txt", "agents": "README.md", "foundations": "FOUNDATIONS.md"}
_AGENT_HEADING = "## For AI agents"


def _read(name: str) -> str:
    here = Path(__file__).resolve().parent.parent
    for path in (
        here / "_docs" / name,
        here.parent.parent / name,
        here.parent.parent / "docs" / name,
    ):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"{name} isn't bundled with this install of latris.")


def read_docs(topic: str = "agents") -> str:
    """``agents``: the README's "For AI agents" section; ``readme``; ``llms`` (llms.txt);
    ``foundations`` (the methods-and-foundations reference)."""
    if topic not in TOPICS:
        raise ValueError(f"topic must be one of: {', '.join(TOPICS)}")
    text = _read(_FILES[topic])
    if topic != "agents":
        return text
    start = text.find(_AGENT_HEADING)
    if start < 0:
        return text
    end = text.find("\n## ", start + len(_AGENT_HEADING))
    return text[start : end if end > 0 else len(text)].rstrip() + "\n"
