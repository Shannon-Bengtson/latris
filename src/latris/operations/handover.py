"""Is this model ready to hand to a board? One pre-flight list.

Everything here is already in the project — this only gathers it: links
nobody has sourced, citations nobody has checked against their source,
cited sources with nothing on file showing they were read, checks resting
on a quote that isn't in the source's stored text, findings waiting for a
person's approval, report sections without prose or with prose the model
has outgrown, descriptions that contradict their link's polarity, and
broken references between files (``check_integrity``). Each item says how
to fix it. Contested links aren't on the list: showing both sides is the
point, not a gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from latris.repo.project import require_project
from latris.repo.yaml_io import load_model

# Where each item is put right, for a surface to take the reader there: the links' sources, the source
# library, the findings, the interpretation, the recorded results, a model type's own check, the choice of
# model types (approach), or the files.
Area = Literal["links", "sources", "findings", "interpretation", "results", "model", "approach", "files"]


@dataclass
class HandoverItem:
    # unsourced_links | unchecked_citations | unread_sources | unfound_quotes | unapproved_findings
    # | findings_about_removed | missing_prose | stale_prose | contradictions | stale_results
    # | exploratory_results | model_incomplete | missing_rationale | integrity
    kind: str
    count: int
    message: str
    fix: str  # what to do, in plain words
    command: str  # how, from the command line
    area: Area
    examples: list[str] = field(default_factory=list)
    target_ids: list[str] = field(default_factory=list)  # the factors and links concerned, every one
    model_type: str | None = None  # the type whose check it is (model_incomplete)


@dataclass
class HandoverReport:
    model_type: str  # the types checked, comma-separated ("cld,sd,bn")
    ready: bool
    items: list[HandoverItem]
    model_types: list[str] = field(default_factory=list)


def handover_check(*, model_type: str | None = None, root: Path | None = None) -> HandoverReport:
    """What's left before a board sees the model — for ``model_type``, or every model type it is."""
    from latris.operations.analysis import run_coherence_check
    from latris.operations.findings import list_findings
    from latris.operations.interpret import _coverage_ids, _element_names, _for_ids, load_interpretation
    from latris.operations.interpret_registry import INTERPRET_SECTION_REGISTRY
    from latris.schema import EvidenceLinkSet, ProjectFoundation, Substrate

    paths = require_project(root)
    foundation = load_model(ProjectFoundation, paths.project_yaml)
    types = [model_type] if model_type else (list(foundation.selected_model_types) or ["cld"])
    several = len(types) > 1
    substrate = load_model(Substrate, paths.conceptual_yaml)
    evidence = (
        load_model(EvidenceLinkSet, paths.evidence_links_yaml)
        if paths.evidence_links_yaml.exists() else EvidenceLinkSet()
    )
    items: list[HandoverItem] = []
    element_ids = {e.id for e in substrate.entities} | {e.id for e in substrate.edges}

    covered, noun = _coverage_ids(substrate, paths)
    unsourced = sorted(covered - _for_ids(evidence))
    if unsourced:
        items.append(HandoverItem(
            "unsourced_links", len(unsourced),
            f"{len(unsourced)} of {len(covered)} {noun} {'has' if len(unsourced) == 1 else 'have'} no source",
            fix="cite a source for each, mark one true by definition, or record it as an assumption",
            command="`latris evidence add <link> polarity <key>`; `latris attr set <link> confidence by-definition`",
            area="links",
            examples=_element_names(substrate, unsourced)[:5],
            target_ids=unsourced,
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
            fix="read each source and say whether it supports the link, argues against it, or is off topic",
            command="`latris evidence check <link> polarity <key> supports|against|off-topic --rationale \"...\"`",
            area="sources",
            examples=[f"{e.bibkey} on {names.get(e.target_id, 'the model')}" for e in unchecked[:5]],
            target_ids=_unique(e.target_id for e in unchecked if e.target_id),
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
            fix="save the passage you read, or fetch the source; correct a wrong DOI or URL, or drop a source "
            "you can't use",
            command="`latris ref snapshot <key> --url <where> --kind abstract --extract \"...\"`; "
            "`latris ref fetch <key>`; `latris ref edit`; `latris ref remove`",
            area="sources",
            examples=[_cite_name(refs[k]) for k in unread[:5]],
            target_ids=_unique(e.target_id for e in evidence.entries if e.bibkey in unread and e.target_id),
        ))

    unfound = [e for e in evidence.entries if e.quote and e.quote_verified is not True]
    if unfound:
        items.append(HandoverItem(
            "unfound_quotes", len(unfound),
            f"{len(unfound)} check{'s rest' if len(unfound) != 1 else ' rests'} on a quote that isn't in the "
            "source's stored text (the report says so)",
            fix="save the passage you read, then check again with the quote copied from it; or set the check "
            "back to unchecked",
            command="`latris ref snapshot`; `latris evidence check <link> polarity <key> unchecked -r \"...\"`",
            area="sources",
            examples=[f"{e.bibkey}: \"{e.quote[:60]}\"" for e in unfound[:5]],
            target_ids=_unique(e.target_id for e in unfound if e.target_id),
        ))

    waiting = [
        f for f in list_findings(model_type=None if several else types[0], root=paths.root)
        if f.maturity in ("proposed", "reviewed") and f.model_type in types
    ]
    if waiting:
        items.append(HandoverItem(
            "unapproved_findings", len(waiting),
            f"{len(waiting)} finding{'s' if len(waiting) != 1 else ''} waiting for a person's approval "
            "(the client report leaves them out)",
            fix="a person reads each and approves it, or drops it",
            command="`latris mature approve <finding-id>`",
            area="findings",
            examples=[f"{f.statement} ({f.model_type})" if several else f.statement for f in waiting[:5]],
            target_ids=_unique(t for f in waiting for t in f.target_ids if t in element_ids),
        ))

    from latris.operations.interpret_registry import MODEL_WIDE

    orphaned = [f for f in list_findings(model_type=None, root=paths.root)
                if f.model_type in types
                and any(t not in element_ids for t in f.target_ids)]
    if orphaned:
        items.append(HandoverItem(
            "findings_about_removed", len(orphaned),
            f"{len(orphaned)} finding{'s are' if len(orphaned) != 1 else ' is'} about a factor or link that has "
            "since been removed, so the report may describe something no longer in the model",
            fix="rewrite each as a new finding about what's there now, or drop it",
            command="`latris finding add`",
            area="findings",
            examples=[f.statement for f in orphaned[:5]],
        ))

    sections = [s for s in load_interpretation(root=paths.root).sections if s.model_type in (*types, MODEL_WIDE)]
    if not sections:
        items.append(HandoverItem(
            "missing_prose", 1, "the interpretation (the answer, implications, confidence) hasn't been started",
            fix="start the interpretation and write each section",
            command="`latris interpret initialise`, then `latris interpret show <section>` and "
            "`latris interpret set-prose <section> \"...\" --by ai`",
            area="interpretation",
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
                fix="write each one from its claims",
                command="`latris interpret show <section>`, then "
                "`latris interpret set-prose <section> \"...\" --by ai`",
                area="interpretation",
                examples=[f"{n} ({s.model_type})" if several and s.model_type != MODEL_WIDE else n
                          for n, s in zip(names, empty, strict=True)][:5],
            ))

    from latris.operations.interpret import extract_claims

    stale = [s for s in sections if s.is_stale(extract_claims(s.section_type, s.model_type, root=paths.root))]
    if stale:
        items.append(HandoverItem(
            "stale_prose", len(stale),
            f"{len(stale)} report section{'s were' if len(stale) != 1 else ' was'} written before the model "
            f"last changed, and the claims behind {'them' if len(stale) != 1 else 'it'} have changed",
            fix="refresh the claims, then rewrite each section from them",
            command="`latris interpret refresh-claims`, then `latris interpret show <section>` and rewrite it "
            "with `latris interpret set-prose`",
            area="interpretation",
            examples=[
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
            fix="fix the description or the polarity of each",
            command="`latris check coherence` lists them",
            area="links",
            examples=_element_names(substrate, [c.target_id for c in likely])[:5],
            target_ids=_unique(c.target_id for c in likely if c.target_id),
        ))

    from latris.operations.analysis_results import report_results

    shown = report_results(model_types=types, root=paths.root)
    out_of_date = [r for r in shown if r.stale]
    if out_of_date:
        items.append(HandoverItem(
            "stale_results", len(out_of_date),
            f"{len(out_of_date)} result{'s' if len(out_of_date) != 1 else ''} in the report "
            f"{'were' if len(out_of_date) != 1 else 'was'} computed before the model last changed",
            fix="run each analysis again, or leave it out of the report",
            command="re-run it (e.g. `latris sd simulate`, `latris sd monte-carlo`), or `latris results hide <run>`",
            area="results",
            examples=[r.run.output_summary[:120] for r in out_of_date[:5]],
        ))

    from latris.operations.sd_scenarios import WHAT_IF

    exploratory = [r for r in shown if r.run.result_kind == "sd-simulation" and f'"{WHAT_IF}' in r.run.analysis_key]
    if exploratory:
        items.append(HandoverItem(
            "exploratory_results", len(exploratory),
            f"{len(exploratory)} simulation{'s' if len(exploratory) != 1 else ''} in the report "
            f"{'include' if len(exploratory) != 1 else 'includes'} an unsaved what-if",
            fix="save the values as a scenario and run it again, or leave the run out of the report",
            command="`latris sd set-scenario`, then re-run; or `latris results hide <run>`",
            area="results",
            examples=[r.run.output_summary[:120] for r in exploratory[:5]],
        ))

    from latris.operations import formalisms
    from latris.schema import Substrate
    from latris.schema.model_types import get_model_type

    for mt in types:
        plugin = formalisms.get(mt)
        if not (plugin and plugin.spec_field and plugin.structure_problems):
            continue  # the causal types' structure is the readiness check's
        problems = plugin.structure_problems(paths.root)
        if problems:
            labels = formalisms.problem_labels(load_model(Substrate, paths.conceptual_yaml))
            how = f"`latris {plugin.cli[1]} check` lists each gap and how to fix it" if plugin.cli else ""
            items.append(HandoverItem(
                "model_incomplete", len(problems),
                f"the {get_model_type(mt).display_name} model doesn't pass its check ({len(problems)} gap"
                f"{'s' if len(problems) != 1 else ''})",
                fix="fill each gap its check lists",
                command=how,
                area="model",
                examples=[f"{labels[p.target_id]}: {p.message}" if p.target_id in labels else p.message
                          for p in problems[:5]],
                target_ids=_unique(p.target_id for p in problems if p.target_id in labels),
                model_type=mt,
            ))

    from latris.operations.project import current_model_choices

    choices = current_model_choices(root=paths.root)
    unexplained = [m for m in types if not (choices.get(m) and choices[m].rationale.strip())]
    if unexplained:
        items.append(HandoverItem(
            "missing_rationale", len(unexplained),
            f"no reason recorded for choosing {len(unexplained)} model type{'s' if len(unexplained) != 1 else ''} "
            "(the report's Modelling Approach section)",
            fix="say why each model type suits the question",
            command="`latris project choose <type> --why \"...\"`",
            area="approach",
            examples=[get_model_type(m).display_name for m in unexplained[:5]],
        ))

    from latris.operations.integrity import check_integrity

    broken = check_integrity(root=paths.root).errors
    if broken:
        items.append(HandoverItem(
            "integrity", len(broken),
            f"{len(broken)} broken reference{'s' if len(broken) != 1 else ''} in the project files "
            "(something points at a node, link, source or dataset that isn't there)",
            fix="remove the rows left behind by deleted factors and links, and correct the rest",
            command="`latris check integrity` lists each one; `latris check integrity --fix` removes rows "
            "left behind by deleted nodes and links",
            area="files",
            examples=[f"{p.where}: {p.message}" for p in broken[:5]],
        ))

    return HandoverReport(model_type=",".join(types), ready=not items, items=items, model_types=types)


def _unique(ids) -> list[str]:
    return list(dict.fromkeys(ids))


def _cite_name(ref) -> str:
    first = (ref.authors or [""])[0].split(",")[0].strip()
    return f"{ref.bibkey} ({first} {ref.year or ''})".replace(" )", ")").replace("( ", "(") if first else ref.bibkey
