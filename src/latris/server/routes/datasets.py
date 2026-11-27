"""Dataset endpoints — upload, operations, columns, versions, preview."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel

from latris.operations import datasets as ds_ops
from latris.schema.data_actions import DataActionLog
from latris.server.deps import Root

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# Where each route sits in the workflow (schema/workflow.py; rules in docs/engineering/WORKFLOW_STRUCTURE.md).
PLACE = "data"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ApplyOperationRequest(BaseModel):
    kind: str
    params: dict


class UpdateColumnRequest(BaseModel):
    """Either or both: a field left out is left as it is (null clears it)."""

    role: str | None = None
    description: str | None = None


class CreateVersionRequest(BaseModel):
    name: str
    description: str = ""


# ---------------------------------------------------------------------------
# Dataset lifecycle
# ---------------------------------------------------------------------------


def _free_name(stem: str, root: Path) -> str:
    taken = {d.name for d in ds_ops.list_datasets(root)}
    name, n = stem, 2
    while name in taken:
        name, n = f"{stem} ({n})", n + 1
    return name


@router.get("")
def list_datasets(root: Root) -> list[dict[str, Any]]:
    return [d.model_dump(mode="json") for d in ds_ops.list_datasets(root)]


@router.post("/upload", status_code=201)
async def upload_dataset(
    root: Root,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    description: str = Form(""),
) -> dict[str, Any]:
    # Write the uploaded file to a temp location, then call the operation.
    # The dataset is named after the file the person chose (never the temp file); a second upload of the
    # same file name gets a number.
    if not (name and name.strip()):
        name = _free_name(Path(file.filename or "upload.csv").stem.strip() or "dataset", root)
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
    kwargs: dict[str, Any] = {k: getattr(body, k) for k in body.model_fields_set}

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


@router.get("/{dataset_id}/actions", response_model=DataActionLog)
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
