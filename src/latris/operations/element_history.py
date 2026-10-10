"""Per-element git history snippet for AI prompt context (Phase 5c).

Surfaces the commit subject + rationale lines from prior mutations on a
single element. Used by element-scope context builders (`_build_challenge`,
`_build_challenge_edge`, `_build_evidence_demote`,
`_build_verify_claim_against_source`, `_build_steelman`) to give the
model visibility into prior reviewer rationales.

The rationale lines are the ones I plumbed through `auto_commit` bodies
in Phase 3+ (e.g., `remove_edge(rationale=...)` writes
``rationale: ...`` into the commit body). This module reads them back.

Budget (enforced by callers / tests):
- ≤ 50 ms total git overhead per call
- ≤ 200 tokens (~150 words) per emitted snippet
"""

from __future__ import annotations

import re
from pathlib import Path

from latris.repo import git as _git
from latris.repo.project import require_project

_RATIONALE_RE = re.compile(r"^rationale:\s*(.+)$", re.MULTILINE)
_DEFAULT_RECENT = 3
_MAX_WORDS = 150
_MAX_SUBJECT_CHARS = 90
_MAX_RATIONALE_CHARS = 140


def _files_for_element(element_id: str, paths) -> list[Path]:
    """Identify which YAML files mention this element by ID.

    Returns relative paths suitable for `git log -- <path>` filters.
    """
    candidates = [
        paths.conceptual_yaml,
        paths.evidence_links_yaml,
    ]
    out: list[Path] = []
    for f in candidates:
        if not f.exists():
            continue
        try:
            if element_id in f.read_text(encoding="utf-8"):
                out.append(f)
        except OSError:
            continue
    return out


def _extract_rationale(commit_body: str) -> str | None:
    """Pull the first ``rationale:`` line out of an auto_commit body."""
    if not commit_body:
        return None
    m = _RATIONALE_RE.search(commit_body)
    if not m:
        return None
    return m.group(1).strip()


def element_history_snippet(
    element_id: str,
    *,
    recent_commits: int = _DEFAULT_RECENT,
    root: Path | None = None,
) -> str | None:
    """Return a short formatted history block for ``element_id``.

    Joins ``git log --follow`` over files containing the element with
    body-rationale extraction. Returns ``None`` when the element has no
    relevant commit history yet (newly created, unstaged, or no
    rationale-bearing commits).

    Snippet shape (≤ 200 tokens):

        - 2026-05-09: Retyped edge "A" → "B": causal → decision_rule
          Rationale: counts as policy lever, not feedback mechanism
        - 2026-05-08: Set polarity on edge_…: -
    """
    paths = require_project(root)
    files = _files_for_element(element_id, paths)
    if not files:
        return None

    # Relative paths for git (forward slashes, repo-relative).
    rel_paths: list[str] = []
    for f in files:
        try:
            rel = f.relative_to(paths.root)
        except ValueError:
            continue
        rel_paths.append(str(rel).replace("\\", "/"))
    if not rel_paths:
        return None

    # One git log call covers all files. `--format` uses null bytes as
    # field separators so we can split safely without false-positives on
    # newlines inside commit messages.
    # `--follow` only works with a single pathspec, so use it only in
    # that case; with multiple files we accept the (rare) case of
    # rename-blindness in exchange for a single log call.
    follow_arg = ["--follow"] if len(rel_paths) == 1 else []
    try:
        out = _git.run_git(
            [
                "log",
                *follow_arg,
                f"-{recent_commits * len(rel_paths) * 4}",  # generous; we filter
                "--format=__COMMIT__%x00%H%x00%aI%x00%s%x00%b%x00__END__",
                "--",
                *rel_paths,
            ],
            cwd=paths.root,
        ).stdout
    except Exception:  # noqa: BLE001 — history is an optional context block
        return None
    if not out:
        return None

    # Parse: each record is __COMMIT__\0<sha>\0<iso-date>\0<subject>\0<body>\0__END__
    records: list[tuple[str, str, str, str]] = []
    for chunk in out.split("__COMMIT__"):
        chunk = chunk.strip("\x00 \n\r")
        if not chunk:
            continue
        parts = chunk.split("\x00")
        if len(parts) < 4:
            continue
        sha, iso_date, subject = parts[0].strip(), parts[1].strip(), parts[2].strip()
        body = "\n".join(p for p in parts[3:] if not p.startswith("__END__"))
        records.append((sha, iso_date, subject, body))

    # Filter to commits whose subject or body actually references the
    # element_id (otherwise we'd surface unrelated mutations to the same
    # file). Surface at most `recent_commits` lines.
    matching: list[str] = []
    for sha, iso_date, subject, body in records:  # noqa: B007
        if element_id not in subject and element_id not in body:
            continue
        date = iso_date.split("T", 1)[0]
        subject_short = subject if len(subject) <= _MAX_SUBJECT_CHARS else (subject[: _MAX_SUBJECT_CHARS - 1] + "…")
        line = f"- {date}: {subject_short}"
        rationale = _extract_rationale(body)
        if rationale:
            rationale_short = rationale if len(rationale) <= _MAX_RATIONALE_CHARS else (rationale[: _MAX_RATIONALE_CHARS - 1] + "…")  # noqa: E501
            line += f"\n  Rationale: {rationale_short}"
        matching.append(line)
        if len(matching) >= recent_commits:
            break

    if not matching:
        return None

    block = "## Recent history for this element\n" + "\n".join(matching) + "\n"
    # Enforce token-budget cap (~150 words). Truncate the tail if over.
    words = block.split()
    if len(words) > _MAX_WORDS:
        block = " ".join(words[:_MAX_WORDS]) + "…\n"
    return block
