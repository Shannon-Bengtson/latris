"""Comparing options: what each one is measured against, and how a difference is worded.

Shared by SD (``sd compare``) and BN (``bn compare``) so both name the reference on every row the
same way: an option that ``extends`` a compared option is measured against it (delayed vs
undelayed — the cost of waiting), every other option against the baseline (no scenario changes),
unless one reference is given for all.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Named(Protocol):
    name: str
    extends: str | None


_DEFERRAL = ("delay", "defer", "later", "postpone", "wait")


def references(
    options: Sequence[Named], reference: str | None,
) -> tuple[dict[str, str], list[str], str | None]:
    """Each arm's reference, warnings about comparisons likely to be misread, and the explicit reference
    in its canonical spelling."""
    names = {sc.name.lower(): sc.name for sc in options}
    warnings: list[str] = []
    if reference is not None:
        if reference.strip().lower() == "baseline":
            reference = "baseline"
        elif reference.strip().lower() in names:
            reference = names[reference.strip().lower()]
        else:
            raise ValueError(
                f"the reference {reference!r} must be 'baseline' or one of the compared scenarios: "
                + ", ".join(sc.name for sc in options)
            )
    out: dict[str, str] = {}
    if reference is not None and reference != "baseline":
        out["baseline"] = reference
    for sc in options:
        if sc.name == reference:
            continue
        parent = names.get((sc.extends or "").lower())
        if reference is not None:
            out[sc.name] = reference
        elif parent:
            out[sc.name] = parent
        else:
            out[sc.name] = "baseline"
        if sc.extends and not parent and reference is None:
            warnings.append(
                f"{sc.name} extends {sc.extends}, which isn't in this comparison, so it is measured against the "
                f"baseline (no scenario changes), not against {sc.extends}. Add {sc.extends} to compare them directly."
            )
        elif not sc.extends and out[sc.name] == "baseline" and any(w in sc.name.lower() for w in _DEFERRAL):
            warnings.append(
                f"{sc.name} sounds like a delayed or deferred option but is measured against the baseline "
                "(no scenario changes). For the cost of waiting, save it with extends=<the undelayed option> "
                "and compare both."
            )
    return out, warnings, reference


def arm_label(name: str) -> str:
    """How an arm is named in prose: the baseline says what it is."""
    return "the baseline (no scenario changes)" if name == "baseline" else name


def share_text(d: dict[str, float]) -> str:
    lo, hi = d["share_lower"], d["share_higher"]
    same = max(0.0, 1 - lo - hi)
    parts = [f"lower in {lo:.0%} of draws", f"higher in {hi:.0%}"]
    if same >= 0.005:
        parts.append(f"unchanged in {same:.0%}")
    return ", ".join(parts)


