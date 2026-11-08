"""Evidence link operations — attach citations to (target, attribute) pairs.

Per the concept doc: citations attach to attributes, not bare entities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from latris.operations._resolve import resolve_target as _resolve_target_id
from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    DataLink,
    DataLinkSet,
    DatasetLibrary,
    EvidenceLink,
    EvidenceLinkSet,
    Informants,
    ReferenceLibrary,
    Substrate,
    SupportVerdict,
)
from latris.schema.common import default_origin


def _load_library(paths) -> ReferenceLibrary:
    if not paths.references_yaml.exists():
        return ReferenceLibrary()
    return load_model(ReferenceLibrary, paths.references_yaml)


def add_evidence(
    target: str | None,
    attribute: str,
    bibkey: str,
    *,
    verified_by: Literal["human", "ai"] = "human",
    informants: Informants | None = None,
    notes: str | None = None,
    contradicts: bool = False,
    root: Path | None = None,
) -> tuple[EvidenceLink, str]:
    """Cite ``bibkey`` on a (target, attribute) claim.

    ``contradicts=True`` records a source that argues *against* the claim
    (``stance="against"``): it stays on the same link as the supporting
    sources, so reports can show both sides. Like any citation it is not
    yet checked; ``set_evidence_support_verdict`` records a check.
    """
    paths = require_project(root)

    if target:
        substrate = load_model(Substrate, paths.conceptual_yaml)
        target_id: str | None = _resolve_target_id(target, substrate)
    else:
        target_id = None

    library = _load_library(paths)
    matching_ref = next((r for r in library.entries if r.bibkey == bibkey), None)
    if matching_ref is None:
        raise ValueError(
            f"unknown reference {bibkey!r}. Add it first with `latris ref add {bibkey} --title ...`"
        )

    store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)

    dup = next(
        (e for e in store.entries if e.target_id == target_id and e.attribute == attribute and e.bibkey == bibkey),
        None,
    )
    if dup is not None:
        label = f"{target_id} / {attribute}" if target_id else f"model / {attribute}"
        raise ValueError(f"evidence {bibkey!r} is already attached to {label}")

    # Phase 2: promote `source_access` to `"abstract"` when the
    # Reference has an abstract or an abstract/full-text snapshot.
    # Landing-page-text snapshots stay at `"title_only"`. Phase 4
    # promotes further to full_text_chunk via apply()-time quote
    # validation.
    from latris.operations.references import compute_source_access

    source_access = compute_source_access(matching_ref)

    link = EvidenceLink(
        target_id=target_id,
        attribute=attribute,
        bibkey=bibkey,
        informants=informants or Informants(),
        notes=notes,
        verified_by=verified_by,
        source_access=source_access,
        stance="against" if contradicts else "for",
        origin=default_origin(),
    )
    store.entries.append(link)
    dump_model(store, paths.evidence_links_yaml)

    target_label = f"{target_id[:15]}…" if target_id else "model"
    sha = auto_commit(
        paths.root,
        subject=f'Attached {"contradicting " if contradicts else ""}evidence "{bibkey}" to {target_label}/{attribute}',
        body=f"target: {target_id or 'model'}\nattribute: {attribute}\nverified_by: {verified_by}",
        paths=[paths.evidence_links_yaml],
    )
    return link, sha


def _resolve_link(
    store: EvidenceLinkSet,
    target: str | None,
    attribute: str,
    bibkey: str,
    paths,
) -> EvidenceLink:
    if target is None:
        target_id: str | None = None
    else:
        substrate = load_model(Substrate, paths.conceptual_yaml)
        target_id = _resolve_target_id(target, substrate)
    match = next(
        (
            e
            for e in store.entries
            if e.target_id == target_id and e.attribute == attribute and e.bibkey == bibkey
        ),
        None,
    )
    if match is None:
        label = f"{target_id} / {attribute}" if target_id else f"model / {attribute}"
        raise ValueError(f"no evidence link {bibkey!r} on {label}")
    return match


def remove_evidence(
    target: str | None,
    attribute: str,
    bibkey: str,
    *,
    rationale: str | None = None,
    root: Path | None = None,
) -> tuple[EvidenceLink, str]:
    """Detach an evidence link by (target, attribute, bibkey).

    The rationale is written into the commit body when present —
    that's the audit record (per the git-native design).
    """
    paths = require_project(root)
    store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    link = _resolve_link(store, target, attribute, bibkey, paths)
    store.entries = [
        e
        for e in store.entries
        if not (e.target_id == link.target_id and e.attribute == link.attribute and e.bibkey == link.bibkey)
    ]
    dump_model(store, paths.evidence_links_yaml)

    target_label = f"{link.target_id[:15]}…" if link.target_id else "model"
    body = f"target: {link.target_id or 'model'}\nattribute: {link.attribute}\nbibkey: {link.bibkey}"
    if rationale:
        body += f"\nrationale: {rationale}"
    sha = auto_commit(
        paths.root,
        subject=f'Detached evidence "{bibkey}" from {target_label}/{attribute}',
        body=body,
        paths=[paths.evidence_links_yaml],
    )
    return link, sha


def set_evidence_support_verdict(
    target: str | None,
    attribute: str,
    bibkey: str,
    *,
    new_verdict: SupportVerdict,
    rationale: str,
    quote: str | None = None,
    checked_by: Literal["human", "ai"] | None = None,
    root: Path | None = None,
) -> tuple[EvidenceLink, str]:
    """Record a check: whether the source supports the claim it is cited for.

    ``checked_by`` (a person reading the source, or an AI) is recorded in
    the note; ``verified_by`` keeps saying who attached the citation.
    The rationale is appended to ``notes``, so the audit chain stays in the
    YAML alongside the commit message.

    A ``quote`` is looked up in the text Latris holds for the source
    (``_quotes.locate_quote``). Found: the quote, its location and what it
    was found in (``source_access``) are recorded, ``quote_verified=True``.
    Not found: an AI's check is refused (a paraphrase is not a quote); a
    person's is recorded with ``quote_verified=False``, since they may have
    read text Latris doesn't hold. An AI's "supports" needs a quote.
    """
    from latris.operations._quotes import has_stored_text, locate_quote

    paths = require_project(root)
    store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    link = _resolve_link(store, target, attribute, bibkey, paths)
    old_verdict = link.support_verdict
    if old_verdict == new_verdict and (quote is None or quote == link.quote):
        raise ValueError(
            f"evidence {bibkey!r} on {link.target_id or 'model'}/{attribute} "
            f"already has support_verdict {new_verdict!r}"
        )
    if checked_by == "ai" and new_verdict == "supports" and not quote:
        raise ValueError(
            "an AI's check that a source supports a claim needs --quote: a passage copied from the source"
        )

    match = None
    if quote:
        reference = next((r for r in _load_library(paths).entries if r.bibkey == bibkey), None)
        match = locate_quote(quote, reference, paths) if reference is not None else None
        if match is None and checked_by == "ai":
            held = (
                "the text it holds doesn't contain it" if reference is not None and has_stored_text(reference, paths)
                else "it holds no text for this source"
            )
            raise ValueError(
                f"the quote isn't in the text Latris holds for {bibkey!r} ({held}). A quote must be copied "
                "from the source, not paraphrased (at least 20 characters; '...' may mark a gap). Save the "
                f"passage you read first — `latris ref snapshot {bibkey} --url <where you read it> --kind "
                "abstract|full_text_excerpt --extract \"...\"` — then check again. A verdict other than "
                "supports can be recorded without --quote."
            )

    link.support_verdict = new_verdict
    who = {"human": " (checked by a person)", "ai": " (checked by an AI)"}.get(checked_by or "", "")
    note_addition = f"verdict {old_verdict} → {new_verdict}{who}: {rationale}"
    link.notes = f"{link.notes}\n{note_addition}" if link.notes else note_addition

    link.quote = quote or None
    link.quote_location = match.location if match else None
    link.quote_verified = None if not quote else match is not None
    if match is not None:
        # What the check rests on: the text the quote was found in.
        link.source_access = match.tier

    dump_model(store, paths.evidence_links_yaml)

    target_label = f"{link.target_id[:15]}…" if link.target_id else "model"
    subject_verb = (
        "Verified" if new_verdict == "supports" and match is not None
        else "Checked" if checked_by is not None
        else "Demoted"
    )
    body = f"target: {link.target_id or 'model'}\nattribute: {attribute}\nbibkey: {bibkey}\nrationale: {rationale}"
    if quote:
        body += f"\nquote: {'found in ' + match.where if match else 'not found in the stored text'}"
    sha = auto_commit(
        paths.root,
        subject=f'{subject_verb} evidence "{bibkey}" on {target_label}/{attribute}: {old_verdict} → {new_verdict}',
        body=body,
        paths=[paths.evidence_links_yaml],
    )
    return link, sha


def _load_dataset_library(paths) -> DatasetLibrary:
    if not paths.data_datasets_yaml.exists():
        return DatasetLibrary()
    return load_model(DatasetLibrary, paths.data_datasets_yaml)


def add_data_link(
    target: str | None,
    dataset_id: str,
    *,
    column_names: list[str] | None = None,
    statistic: str | None = None,
    value: str | None = None,
    rationale: str | None = None,
    notes: str | None = None,
    root: Path | None = None,
) -> tuple[DataLink, str]:
    """Manually attach a data-evidence link to an element or the model."""
    paths = require_project(root)

    if target:
        substrate = load_model(Substrate, paths.conceptual_yaml)
        target_id: str | None = _resolve_target_id(target, substrate)
    else:
        target_id = None

    library = _load_dataset_library(paths)
    if not any(d.id == dataset_id for d in library.entries):
        raise ValueError(f"unknown dataset {dataset_id!r}. Import a dataset first with `latris data import ...`")

    store = load_model(DataLinkSet, paths.data_links_yaml) if paths.data_links_yaml.exists() else DataLinkSet()

    link = DataLink(
        target_id=target_id,
        attribute="existence",
        dataset_id=dataset_id,
        column_names=column_names or [],
        statistic=statistic,
        value=value,
        rationale=rationale,
        notes=notes,
        origin="human-direct",
    )
    store.entries.append(link)
    dump_model(store, paths.data_links_yaml)

    target_label = f"{target_id[:15]}…" if target_id else "model"
    sha = auto_commit(
        paths.root,
        subject=f"Attached data evidence from {dataset_id[:20]} to {target_label}",
        paths=[paths.data_links_yaml],
    )
    return link, sha
