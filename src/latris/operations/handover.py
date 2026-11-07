"""Is this model ready to hand to a board? One pre-flight list.

Everything here is already in the project — this only gathers it: links
nobody has sourced, citations nobody has checked against their source,
findings waiting for a person's approval, report sections without prose,
and descriptions that contradict their link's polarity. Each item says how
to fix it. Contested links aren't on the list: showing both sides is the
point, not a gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from latris.repo.project import require_project
from latris.repo.yaml_io import load_model


@dataclass
class HandoverItem:
    kind: str  # unsourced_links | unchecked_citations | unapproved_findings | missing_prose | contradictions
    count: int
    message: str
    fix: str
    examples: list[str] = field(default_factory=list)


@dataclass
class HandoverReport:
    model_type: str
    ready: bool
    items: list[HandoverItem]


def handover_check(*, model_type: str | None = None, root: Path | None = None) -> HandoverReport:
    from latris.operations.analysis import run_coherence_check
    from latris.operations.findings import list_findings
    from latris.operations.interpret import _coverage_ids, _element_names, _for_ids, load_interpretation
    from latris.operations.interpret_registry import INTERPRET_SECTION_REGISTRY
    from latris.schema import EvidenceLinkSet, ProjectFoundation, Substrate

    paths = require_project(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    model_type = model_type or next(iter(foundation.selected_model_types), "cld")
    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence = (
        load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        if paths.evidence_links_yaml.exists() else EvidenceLinkSet()
    )
    items: list[HandoverItem] = []

    covered, noun = _coverage_ids(substrate, paths)
    unsourced = sorted(covered - _for_ids(evidence))
    if unsourced:
        items.append(HandoverItem(
            "unsourced_links", len(unsourced),
            f"{len(unsourced)} of {len(covered)} {noun} {'has' if len(unsourced) == 1 else 'have'} no source",
            "cite one (`latris evidence add <link> polarity <key>`), mark a link true by definition "
            "(`latris attr set <link> confidence by-definition`), or record it as an assumption",
            _element_names(substrate, unsourced)[:5],
        ))

    unchecked = [e for e in evidence.entries if e.support_verdict == "unverified"]
    if unchecked:
        names = dict(zip(
            [e.target_id for e in unchecked if e.target_id],
            _element_names(substrate, [e.target_id for e in unchecked if e.target_id]),
            strict=True,
        ))
        cited = [e for e in evidence.entries if e.support_verdict != "contradicts"]
        items.append(HandoverItem(
            "unchecked_citations", len(unchecked),
            f"{len(unchecked)} of {len(cited)} citations {'hasn' if len(unchecked) == 1 else 'haven'}'t been "
            "checked against their source",
            "read each source, then `latris evidence check <link> polarity <key> supports|against|off-topic "
            "--rationale \"...\"`",
            [f"{e.bibkey} on {names.get(e.target_id, 'the model')}" for e in unchecked[:5]],
        ))

    waiting = [
        f for f in list_findings(model_type=model_type, root=paths.root) if f.maturity in ("proposed", "reviewed")
    ]
    if waiting:
        items.append(HandoverItem(
            "unapproved_findings", len(waiting),
            f"{len(waiting)} finding{'s' if len(waiting) != 1 else ''} waiting for a person's approval "
            "(the client report leaves them out)",
            "a person reads each and runs `latris mature approve <finding-id>` (or drops it)",
            [f.statement for f in waiting[:5]],
        ))

    sections = [s for s in load_interpretation(root=paths.root).sections if s.model_type == model_type]
    if not sections:
        items.append(HandoverItem(
            "missing_prose", 1, "the interpretation (the answer, implications, confidence) hasn't been started",
            "`latris interpret initialise`, then `latris interpret show <section>` and "
            "`latris interpret set-prose <section> \"...\" --by ai`",
        ))
    else:
        empty = [s for s in sections if not s.prose.strip()]
        if empty:
            names = [
                INTERPRET_SECTION_REGISTRY[s.section_type].display_name
                if s.section_type in INTERPRET_SECTION_REGISTRY else s.section_type
                for s in empty
            ]
            items.append(HandoverItem(
                "missing_prose", len(empty),
                f"{len(empty)} of {len(sections)} report sections have no prose (readers see raw claims)",
                "`latris interpret show <section>`, then `latris interpret set-prose <section> \"...\" --by ai`",
                names[:5],
            ))

    likely = [c for c in run_coherence_check(root=paths.root) if c.severity == "likely"]
    if likely:
        items.append(HandoverItem(
            "contradictions", len(likely),
            f"{len(likely)} link{'s' if len(likely) != 1 else ''} where the description and the polarity "
            "tell opposite stories",
            "`latris check coherence` lists them; fix the description or the polarity",
            _element_names(substrate, [c.target_id for c in likely])[:5],
        ))

    return HandoverReport(model_type=model_type, ready=not items, items=items)
