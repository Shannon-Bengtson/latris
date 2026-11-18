"""Interpretation claims drawn from recorded results (simulations, uncertainty, loops).

Claims are what the model supports — the interpretation's prose must stick to
them. Structural claims come from the diagram; these come from the numbers:
what a simulation shows, what each scenario changes, how wide the uncertainty
is and what drives it, which loop dominates. Every result kind's claims —
SD's included (``formalisms/sd_results.py``) — live on its ``ResultKind`` hooks. Each claim is
a deterministic sentence built from a recorded result, and results computed
before the model last changed are left out (they no longer describe the
model).

Claims also say when a conclusion rests on something unreviewed — an
influential value nobody has checked, a dominant loop built on unsourced
links — so the open questions surface it.
"""

from __future__ import annotations

from latris.repo.layout import ProjectPaths


def claims_by_section(model_type: str, paths: ProjectPaths) -> dict[str, list[str]]:
    """Claims per interpretation section from the current (non-stale) results of ``model_type``."""
    from collections import defaultdict

    from latris.operations import formalisms
    from latris.operations.analysis_results import report_results

    out: dict[str, list[str]] = defaultdict(list)
    results = [r for r in report_results(model_types=[model_type], root=paths.root) if not r.stale]
    if not results:
        return out
    for r in results:
        kind, p = r.run.result_kind, r.payload
        try:
            found = formalisms.result_kind(kind)
            if found and found[1].claims:
                found[1].claims(p, out)
        except (KeyError, TypeError, ValueError, IndexError):
            continue  # an unreadable result contributes no claims rather than a wrong one
    return out
