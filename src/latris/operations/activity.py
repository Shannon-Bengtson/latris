"""Recent activity, in words a person can read.

Commit subjects name what changed by ID (``Maturity → approved: node_01J…``,
``Set preferred version: version_01J…``): right for the log, where an ID never
goes stale, and unreadable in a list of recent changes. This reads the log and
puts each ID's current name in its place — a factor's label, a link's two ends,
a version's or dataset's name — so history written before this existed reads
well too. An ID that names nothing any more (a factor since removed) becomes
its kind ("a factor").
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from latris.operations._words import a_or_an
from latris.repo import git
from latris.schema.ids import IDKind

_KINDS = sorted(get_args(IDKind), key=len, reverse=True)
# A whole or cut-short ID (subjects truncate them, often with an ellipsis). Crockford base32.
_ID = re.compile(r"\b(" + "|".join(re.escape(k) for k in _KINDS) + r")_([0-9A-HJKMNP-TV-Z]{6,26})(…|\.\.\.)?")

_KIND_WORDS = {
    "node": "a factor",
    "edge": "a link",
    "version": "a version",
    "dataset": "a dataset",
    "analysis-run": "a run",
    "interpret-section": "a section",
    "missing-var": "a suggested factor",
    "data-action": "a data step",
    "data-version": "a dataset version",
    "story-beat": "a beat",
    "story-asset": "a picture",
    "person-input": "an answer",
    "review-session": "a review",
    "elicitation": "an elicitation",
    "interaction": "an AI suggestion",
}


def _names(root: Path) -> dict[str, str]:
    """ID → what a person calls it, for everything that has a name. Best effort: a project that can't be
    read (mid-merge, an older layout) still lists its activity, with kinds in place of names."""
    names: dict[str, str] = {}
    try:
        from latris.operations.nodes import list_nodes

        labels = {n.id: n.label for n in list_nodes(root)}
        names.update({i: f"“{label}”" for i, label in labels.items()})
        from latris.operations.edges import list_edges

        for e in list_edges(root):
            names[e.id] = f"{labels.get(e.from_id, 'a factor')} → {labels.get(e.to_id, 'a factor')}"
    except Exception:  # noqa: BLE001 - naming is a courtesy; the list matters more
        pass
    try:
        from latris.operations.lineage import nodes_and_branches

        names.update({v.id: f"“{v.name}”" for v in nodes_and_branches(root)[0]})
    except Exception:  # noqa: BLE001
        pass
    try:
        from latris.operations.datasets import list_datasets

        names.update({d.id: f"“{d.name}”" for d in list_datasets(root)})
    except Exception:  # noqa: BLE001
        pass
    return names


def readable_subject(subject: str, names: dict[str, str]) -> str:
    """*subject* with each ID replaced by its name (or, failing that, its kind)."""

    def swap(m: re.Match[str]) -> str:
        whole = f"{m.group(1)}_{m.group(2)}"
        if whole in names:
            return names[whole]
        matches = [name for full, name in names.items() if full.startswith(whole)]
        if len(matches) == 1:
            return matches[0]
        return _KIND_WORDS.get(m.group(1)) or a_or_an(m.group(1))

    return _ID.sub(swap, subject)


def recent_activity(root: Path, limit: int = 20) -> list[dict[str, str]]:
    """The *limit* most recent commits (as :func:`latris.repo.git.recent_commits`), subjects made readable."""
    entries = git.recent_commits(root, limit=limit)
    if not any(_ID.search(e["subject"]) for e in entries):
        return entries
    names = _names(root)
    return [{**e, "subject": readable_subject(e["subject"], names)} for e in entries]
