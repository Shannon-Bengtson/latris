"""Reference library endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from latris.operations.references import (
    add_reference,
    fetch_reference_source,
    get_reference,
    import_bibtex,
    import_doi,
    list_references,
    remove_reference,
    search_references,
    set_source_snapshot,
    update_reference,
)
from latris.schema.references import SourceSnapshotKind
from latris.server.deps import Root

router = APIRouter(prefix="/api/references", tags=["references"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "evidence"


# ── Request bodies ───────────────────────────────────────────────────


class AddReferenceRequest(BaseModel):
    bibkey: str
    title: str
    authors: list[str] | None = None
    year: int | None = None
    container: str | None = None
    doi: str | None = None
    url: str | None = None
    notes: str | None = None


class UpdateReferenceRequest(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    container: str | None = None
    doi: str | None = None
    url: str | None = None
    notes: str | None = None


class ImportBibtexRequest(BaseModel):
    bibtex: str


class ImportDoiRequest(BaseModel):
    doi: str


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/search")
def search_refs(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, Any]]:
    """Search OpenAlex for candidate references (not persisted)."""
    candidates = search_references(q, limit=limit)
    return [r.model_dump(mode="json") for r in candidates]


@router.get("")
def list_refs(root: Root) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") for r in list_references(root)]


@router.post("", status_code=201)
def add_ref(body: AddReferenceRequest, root: Root) -> dict[str, Any]:
    ref, sha = add_reference(
        body.bibkey,
        body.title,
        authors=body.authors,
        year=body.year,
        container=body.container,
        doi=body.doi,
        url=body.url,
        notes=body.notes,
        root=root,
    )
    return {"result": ref.model_dump(mode="json"), "commit_sha": sha}


@router.post("/import-bibtex", status_code=201)
def import_bibtex_endpoint(body: ImportBibtexRequest, root: Root) -> dict[str, Any]:
    refs, sha = import_bibtex(body.bibtex, root=root)
    return {
        "result": [r.model_dump(mode="json") for r in refs],
        "count": len(refs),
        "commit_sha": sha,
    }


@router.post("/import-doi", status_code=201)
def import_doi_endpoint(body: ImportDoiRequest, root: Root) -> dict[str, Any]:
    ref, sha = import_doi(body.doi, root=root)
    return {"result": ref.model_dump(mode="json"), "commit_sha": sha}


@router.get("/{bibkey}")
def get_ref(bibkey: str, root: Root) -> dict[str, Any]:
    ref = get_reference(bibkey, root=root)
    return ref.model_dump(mode="json")


@router.put("/{bibkey}")
def update_ref(bibkey: str, body: UpdateReferenceRequest, root: Root) -> dict[str, Any]:
    ref, sha = update_reference(
        bibkey,
        title=body.title,
        authors=body.authors,
        year=body.year,
        container=body.container,
        doi=body.doi,
        url=body.url,
        notes=body.notes,
        root=root,
    )
    return {"result": ref.model_dump(mode="json"), "commit_sha": sha}


@router.delete("/{bibkey}")
def remove_ref(bibkey: str, root: Root) -> dict[str, Any]:
    ref, sha = remove_reference(bibkey, root=root)
    return {"result": ref.model_dump(mode="json"), "commit_sha": sha}


class FetchSourceRequest(BaseModel):
    url: str | None = None


@router.post("/{bibkey}/fetch")
def fetch_source(bibkey: str, body: FetchSourceRequest, root: Root) -> dict[str, Any]:
    """Phase 4b — Tier-1 fetch.

    Fetches the reference's full text (URL > Reference.url > DOI),
    stores it as a per-bibkey artefact, and updates the
    ``source_snapshot``. Server-side, not auto-fetched at proposal
    time — the user explicitly triggers it.
    """
    ref, sha = fetch_reference_source(bibkey, url=body.url, root=root)
    return {"result": ref.model_dump(mode="json"), "commit_sha": sha}


class SnapshotRequest(BaseModel):
    url: str  # where the passage was read
    extract: str  # the passage, as read (checks' quotes are looked up in it)
    kind: SourceSnapshotKind = "abstract"


@router.post("/{bibkey}/snapshot")
def save_snapshot(bibkey: str, body: SnapshotRequest, root: Root) -> dict[str, Any]:
    """Save what was read of a source — the passage and where — so the report can say a citation was read
    and a check's quote can be found in it."""
    ref, sha = set_source_snapshot(bibkey, retrieval_url=body.url, extract=body.extract, kind=body.kind, root=root)
    return {"result": ref.model_dump(mode="json"), "commit_sha": sha}
