"""Is this model ready to hand to a board? One pre-flight list.

Everything here is already in the project — this only gathers it: links
nobody has sourced, citations nobody has checked against their source,
cited sources with nothing on file showing they were read, checks resting
on a quote that isn't in the source's stored text, findings waiting for a
person's approval, report sections without prose or with prose the model
has outgrown, and descriptions that contradict their link's polarity. Each item says how
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
    # unsourced_links | unchecked_citations | unread_sources | unfound_quotes | unapproved_findings
    # | missing_prose | stale_prose | contradictions | stale_results | model_incomplete
    kind: str
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
        cited = evidence.entries
        items.append(HandoverItem(
            "unchecked_citations", len(unchecked),
            f"{len(unchecked)} of {len(cited)} citations {'hasn' if len(unchecked) == 1 else 'haven'}'t been "
            "checked against their source",
            "read each source, then `latris evidence check <link> polarity <key> supports|against|off-topic "
            "--rationale \"...\"`",
            [f"{e.bibkey} on {names.get(e.target_id, 'the model')}" for e in unchecked[:5]],
        ))

    from latris.operations._quotes import has_stored_text
    from latris.operations.references import load_library

    refs = {r.bibkey: r for r in load_library(paths)[0].entries}
    unread = sorted(
        k for k in {e.bibkey for e in evidence.entries} if k in refs and not has_stored_text(refs[k], paths)
    )
    if unread:
        items.append(HandoverItem(
            "unread_sources", len(unread),
            f"{len(unread)} cited source{'s have' if len(unread) != 1 else ' has'} nothing on file showing "
            "it was read, or that its DOI or URL leads to it",
            "save what you read (`latris ref snapshot <key> --url <where> --kind abstract --extract \"...\"`) "
            "or fetch it (`latris ref fetch <key>`); correct a wrong identifier with `latris ref edit`, "
            "drop an unusable source with `latris ref remove`",
            [_cite_name(refs[k]) for k in unread[:5]],
        ))

    unfound = [e for e in evidence.entries if e.quote and e.quote_verified is not True]
    if unfound:
        items.append(HandoverItem(
            "unfound_quotes", len(unfound),
            f"{len(unfound)} check{'s rest' if len(unfound) != 1 else ' rests'} on a quote that isn't in the "
            "source's stored text (the report says so)",
            "save the passage you read with `latris ref snapshot`, then repeat the check with the quote "
            "copied from it; or reset it (`latris evidence check <link> polarity <key> unchecked -r \"...\"`)",
            [f"{e.bibkey}: \"{e.quote[:60]}\"" for e in unfound[:5]],
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

    from latris.operations.interpret import extract_claims

    stale = [s for s in sections if s.is_stale(extract_claims(s.section_type, s.model_type, root=paths.root))]
    if stale:
        items.append(HandoverItem(
            "stale_prose", len(stale),
            f"{len(stale)} report section{'s were' if len(stale) != 1 else ' was'} written before the model "
            f"last changed, and the claims behind {'them' if len(stale) != 1 else 'it'} have changed",
            "`latris interpret refresh-claims`, then `latris interpret show <section>` and rewrite it with "
            "`latris interpret set-prose`",
            [
                INTERPRET_SECTION_REGISTRY[s.section_type].display_name
                if s.section_type in INTERPRET_SECTION_REGISTRY else s.section_type
                for s in stale[:5]
            ],
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

    from latris.operations.analysis_results import report_results

    out_of_date = [r for r in report_results(model_types=[model_type], root=paths.root) if r.stale]
    if out_of_date:
        items.append(HandoverItem(
            "stale_results", len(out_of_date),
            f"{len(out_of_date)} result{'s' if len(out_of_date) != 1 else ''} in the report "
            f"{'were' if len(out_of_date) != 1 else 'was'} computed before the model last changed",
            "re-run the analysis (e.g. `latris sd simulate`, `latris sd monte-carlo`), or leave it out of the "
            "report with `latris results hide <run>`",
            [r.run.output_summary[:120] for r in out_of_date[:5]],
        ))

    if model_type == "sd":
        from latris.operations import sd as sd_ops

        gaps = sd_ops.check(root=paths.root)
        if gaps:
            items.append(HandoverItem(
                "model_incomplete", len(gaps),
                f"the System Dynamics model doesn't pass its check ({len(gaps)} gap{'s' if len(gaps) != 1 else ''})",
                "`latris sd check` lists each gap and how to fix it",
                [g.message for g in gaps[:5]],
            ))

    return HandoverReport(model_type=model_type, ready=not items, items=items)


def _cite_name(ref) -> str:
    first = (ref.authors or [""])[0].split(",")[0].strip()
    return f"{ref.bibkey} ({first} {ref.year or ''})".replace(" )", ")").replace("( ", "(") if first else ref.bibkey
