"""AI interaction log — write, read, filter.

Every AI call that happens (in a future milestone) gets a record here.
For now the recorder is callable by tests and any future call layer;
no CLI command synthesises a fake interaction.

The log doubles as bespoke project memory: a future retrieval layer will
query by target_id/related_attribute/adoption to assemble context for the
next call. The field is named ``adoption`` (not ``approval``) so the
word "approved" stays reserved for the unified Maturity ladder; see
docs/design/MATURITY_LADDER.md.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_jsonl_append
from latris.schema import AIInteraction, HumanActor, new_id

_RAW_RESPONSE_EXCERPT_LIMIT = 4096


def record_interaction(
    *,
    prompt_name: str,
    prompt_inputs: dict,
    model_id: str,
    response_summary: str,
    response_full: str | None = None,
    target_ids: list[str] | None = None,
    related_attributes: list[str] | None = None,
    proposal_ids: list[str] | None = None,
    token_usage: dict | None = None,
    cost_usd: float | None = None,
    adoption: Literal["pending", "approved", "rejected", "failed"] = "pending",
    error_class: str | None = None,
    error_message: str | None = None,
    raw_response_excerpt: str | None = None,
    commit: bool = True,
    root: Path | None = None,
) -> tuple[AIInteraction, str | None]:
    """Append a new interaction to ``ai/interactions.jsonl``.

    Returns the record and the commit SHA (or ``None`` if ``commit=False``).

    Pass ``adoption="failed"`` with the error fields populated to record an
    adapter-level failure (e.g. structured-output parse error). The
    raw-response excerpt is truncated to 4 KB so the JSONL stays manageable.
    """
    paths = require_project(root)
    record = AIInteraction(
        id=new_id("interaction"),
        prompt_name=prompt_name,
        prompt_inputs=prompt_inputs,
        model_id=model_id,
        target_ids=list(target_ids or []),
        related_attributes=list(related_attributes or []),
        response_summary=response_summary,
        response_full=response_full,
        proposal_ids=list(proposal_ids or []),
        token_usage=dict(token_usage or {}),
        cost_usd=cost_usd,
        adoption=adoption,
        error_class=error_class,
        error_message=error_message,
        raw_response_excerpt=(
            raw_response_excerpt[:_RAW_RESPONSE_EXCERPT_LIMIT]
            if raw_response_excerpt is not None
            else None
        ),
    )
    dump_jsonl_append(record, paths.interactions_jsonl)

    sha: str | None = None
    if commit:
        sha = auto_commit(
            paths.root,
            subject=f"AI interaction: {prompt_name} ({record.adoption})",
            body=f"id: {record.id}\nmodel: {model_id}",
            provenance="ai-proposed",
            paths=[paths.interactions_jsonl],
        )
    return record, sha


def iter_interactions(root: Path | None = None) -> Iterable[AIInteraction]:
    """Iterate validated AIInteraction records."""
    paths = require_project(root)
    if not paths.interactions_jsonl.exists():
        return
    with open(paths.interactions_jsonl, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            yield AIInteraction.model_validate(json.loads(raw))


def list_interactions(
    *,
    target_id: str | None = None,
    prompt_name: str | None = None,
    adoption: Literal["pending", "approved", "rejected"] | None = None,
    limit: int | None = None,
    root: Path | None = None,
) -> list[AIInteraction]:
    """Read the log with optional filters, newest first."""
    records = list(iter_interactions(root=root))
    if target_id is not None:
        records = [r for r in records if target_id in r.target_ids]
    if prompt_name is not None:
        records = [r for r in records if r.prompt_name == prompt_name]
    if adoption is not None:
        records = [r for r in records if r.adoption == adoption]
    records.reverse()  # newest first
    if limit is not None:
        records = records[:limit]
    return records


def get_interaction(
    query: str,
    *,
    root: Path | None = None,
) -> AIInteraction:
    """Return the interaction whose id is ``query`` or whose id starts with it."""
    records = list(iter_interactions(root=root))
    exact = [r for r in records if r.id == query]
    if len(exact) == 1:
        return exact[0]
    prefix = [r for r in records if r.id.startswith(query)]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        ids = ", ".join(r.id for r in prefix)
        raise ValueError(f"interaction prefix {query!r} is ambiguous (matches: {ids})")
    raise ValueError(f"no interaction matches {query!r}")


def set_adoption(
    query: str,
    *,
    adoption: Literal["approved", "rejected"],
    approved_by: HumanActor,
    root: Path | None = None,
) -> tuple[AIInteraction, str]:
    """Update an interaction's adoption state. Rewrites the whole JSONL atomically.

    "approved" / "rejected" here mean "the human adopted the AI proposal"
    or "the human rejected it" — distinct from artifact maturity. See
    docs/design/MATURITY_LADDER.md.
    """
    paths = require_project(root)
    target = get_interaction(query, root=paths.root)
    all_records = list(iter_interactions(root=paths.root))
    for r in all_records:
        if r.id == target.id:
            r.adoption = adoption
            r.approved_by = approved_by
            target = r
            break

    # Rewrite the whole file. Not ideal for huge logs; fine for the prototype.
    tmp = paths.interactions_jsonl.with_suffix(paths.interactions_jsonl.suffix + ".tmp")
    import json

    from ..repo.yaml_io import atomic_replace

    with open(tmp, "w", encoding="utf-8", newline="") as f:
        for r in all_records:
            f.write(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n")
    atomic_replace(tmp, paths.interactions_jsonl)

    sha = auto_commit(
        paths.root,
        subject=f"AI interaction {target.id[:20]}…: {adoption}",
        body=f"prompt: {target.prompt_name}",
        provenance="human-authored",
        paths=[paths.interactions_jsonl],
    )
    return target, sha
