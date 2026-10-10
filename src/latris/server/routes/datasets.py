"""Dataset endpoints — upload, operations, columns, versions, preview."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel

from latris.operations import datasets as ds_ops
from latris.server.deps import get_project_root

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
Root = Annotated[Path, Depends(get_project_root)]


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ApplyOperationRequest(BaseModel):
    kind: str
    params: dict


class UpdateColumnRequest(BaseModel):
    role: str | None = ...  # type: ignore[assignment]
    description: str | None = ...  # type: ignore[assignment]


class CreateVersionRequest(BaseModel):
    name: str
    description: str = ""


# ---------------------------------------------------------------------------
# Dataset lifecycle
# ---------------------------------------------------------------------------


@router.get("")
def list_datasets(root: Root) -> list[dict[str, Any]]:
    return [d.model_dump(mode="json") for d in ds_ops.list_datasets(root)]


@router.post("/upload", status_code=201)
async def upload_dataset(
    root: Root,
    file: UploadFile = File(...),
    name: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    # Write the uploaded file to a temp location, then call the operation.
    suffix = Path(file.filename or "upload.csv").suffix
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
        dir=tempfile.gettempdir(),
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        dataset, sha = ds_ops.upload_dataset(
            tmp_path,
            name=name,
            description=description,
            root=root,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"result": dataset.model_dump(mode="json"), "commit_sha": sha}


# Dynamic path routes MUST come after static ones to avoid /{query}
# swallowing /upload, /stats, etc.


@router.get("/{query}")
def get_dataset(query: str, root: Root) -> dict[str, Any]:
    return ds_ops.get_dataset(query, root=root).model_dump(mode="json")


@router.delete("/{query}")
def remove_dataset(query: str, root: Root) -> dict[str, Any]:
    dataset, sha = ds_ops.remove_dataset(query, root=root)
    return {"result": dataset.model_dump(mode="json"), "commit_sha": sha}


# ---------------------------------------------------------------------------
# Data operations
# ---------------------------------------------------------------------------


@router.post("/{dataset_id}/operations")
def apply_operation(
    dataset_id: str,
    body: ApplyOperationRequest,
    root: Root,
) -> dict[str, Any]:
    action, sha = ds_ops.apply_operation(
        dataset_id,
        body.kind,
        body.params,
        root=root,
    )
    return {"result": action.model_dump(mode="json"), "commit_sha": sha}


# ---------------------------------------------------------------------------
# Column metadata
# ---------------------------------------------------------------------------


@router.patch("/{dataset_id}/columns/{column_name}")
def update_column(
    dataset_id: str,
    column_name: str,
    body: UpdateColumnRequest,
    root: Root,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if body.role is not ...:
        kwargs["role"] = body.role
    if body.description is not ...:
        kwargs["description"] = body.description

    dataset, sha = ds_ops.update_column_metadata(
        dataset_id,
        column_name,
        **kwargs,
        root=root,
    )
    return {"result": dataset.model_dump(mode="json"), "commit_sha": sha}


# ---------------------------------------------------------------------------
# Preview and stats
# ---------------------------------------------------------------------------


@router.get("/{dataset_id}/preview")
def preview_data(
    dataset_id: str,
    root: Root,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=10000),
) -> dict[str, Any]:
    return ds_ops.preview_data(dataset_id, offset=offset, limit=limit, root=root)


@router.get("/{dataset_id}/stats/{column_name}")
def column_stats(
    dataset_id: str,
    column_name: str,
    root: Root,
) -> dict[str, Any]:
    return ds_ops.column_stats(dataset_id, column_name, root=root)


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------


@router.get("/{dataset_id}/actions")
def get_actions(dataset_id: str, root: Root) -> dict[str, Any]:
    log = ds_ops.get_action_log(dataset_id, root=root)
    return log.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


@router.post("/{dataset_id}/versions", status_code=201)
def create_version(
    dataset_id: str,
    body: CreateVersionRequest,
    root: Root,
) -> dict[str, Any]:
    version, sha = ds_ops.version_dataset(
        dataset_id,
        body.name,
        description=body.description,
        root=root,
    )
    return {"result": version.model_dump(mode="json"), "commit_sha": sha}


@router.get("/{dataset_id}/versions")
def list_versions(dataset_id: str, root: Root) -> list[dict[str, Any]]:
    return [v.model_dump(mode="json") for v in ds_ops.list_versions(dataset_id, root=root)]


@router.post("/{dataset_id}/versions/{version_id}/restore")
def restore_version(
    dataset_id: str,
    version_id: str,
    root: Root,
) -> dict[str, Any]:
    dataset, sha = ds_ops.restore_version(
        dataset_id,
        version_id,
        root=root,
    )
    return {"result": dataset.model_dump(mode="json"), "commit_sha": sha}
