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
    QuoteLocation,
    ReferenceLibrary,
    Substrate,
    SupportVerdict,
)


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
    root: Path | None = None,
) -> tuple[EvidenceLink, str]:
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
        support_verdict="unverified",
    )
    store.entries.append(link)
    dump_model(store, paths.evidence_links_yaml)

    target_label = f"{target_id[:15]}…" if target_id else "model"
    sha = auto_commit(
        paths.root,
        subject=f'Attached evidence "{bibkey}" to {target_label}/{attribute}',
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
    quote_location: QuoteLocation | None = None,
    root: Path | None = None,
) -> tuple[EvidenceLink, str]:
    """Mutate `support_verdict` on an existing evidence link.

    Locates the link by (target, attribute, bibkey). Raises ValueError
    on no-op (verdict unchanged). Appends rationale to `notes` so the
    audit chain in the YAML is preserved alongside the commit message.

    When ``new_verdict == "supports"`` and a verbatim ``quote`` (plus
    ``quote_location``) is supplied — i.e. coming from the Phase 4
    apply()-time validator — the quote and its location are written
    onto the link, and ``source_access`` is bumped to
    ``"full_text_chunk"`` if it was previously narrower. Phase 4
    enforces the verbatim invariant; this operation just persists.
    """
    paths = require_project(root)
    store = load_model(EvidenceLinkSet, paths.evidence_links_yaml)
    link = _resolve_link(store, target, attribute, bibkey, paths)
    old_verdict = link.support_verdict
    if old_verdict == new_verdict:
        raise ValueError(
            f"evidence {bibkey!r} on {link.target_id or 'model'}/{attribute} "
            f"already has support_verdict {new_verdict!r}"
        )

    link.support_verdict = new_verdict
    note_addition = f"verdict {old_verdict} → {new_verdict}: {rationale}"
    link.notes = f"{link.notes}\n{note_addition}" if link.notes else note_addition

    if quote is not None:
        link.quote = quote
    if quote_location is not None:
        link.quote_location = quote_location
    # Phase 4: a verbatim-quoted "supports" verdict means the proposer
    # actually saw a chunk of full text. Bump source_access if the
    # prior level was narrower.
    if new_verdict == "supports" and quote is not None and link.source_access in {"title_only", "abstract"}:
        link.source_access = "full_text_chunk"

    dump_model(store, paths.evidence_links_yaml)

    target_label = f"{link.target_id[:15]}…" if link.target_id else "model"
    subject_verb = "Verified" if new_verdict == "supports" and quote is not None else "Demoted"
    sha = auto_commit(
        paths.root,
        subject=f'{subject_verb} evidence "{bibkey}" on {target_label}/{attribute}: {old_verdict} → {new_verdict}',
        body=f"target: {link.target_id or 'model'}\nattribute: {attribute}\nbibkey: {bibkey}\nrationale: {rationale}",
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
