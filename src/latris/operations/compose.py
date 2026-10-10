"""Compose operations — suggest nodes from data, apply staged selections.

The Compose workflow bridges Gather → Build: users curate candidate entities
and edges from gathered evidence (datasets, references, AI synthesis) and
apply them to the substrate in a single commit.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from latris.operations._data_engine import (
    compute_column_stats,
    compute_correlations,
    load_dataframe,
)
from latris.operations.attributes import set_attribute
from latris.operations.batch import batch
from latris.operations.edges import add_edge
from latris.operations.nodes import add_node
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema import (
    DataLink,
    DataLinkSet,
    DatasetLibrary,
    EntityKind,
    Substrate,
    coerce_edge_kind,
    coerce_entity_kind,
)

# ---------------------------------------------------------------------------
# Node suggestions from data
# ---------------------------------------------------------------------------


def suggest_nodes_from_data(
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Extract candidate entity names from dataset column metadata.

    Returns a list of suggestion dicts ready for the frontend:
    ``{id, label, kind, description, source, sourceDetail, stats}``.
    """
    paths = require_project(root)
    if not paths.data_datasets_yaml.exists():
        return []

    library = load_model(DatasetLibrary, paths.data_datasets_yaml)
    if not library.entries:
        return []

    # Load existing substrate labels so we can exclude duplicates.
    existing_labels: set[str] = set()
    if paths.conceptual_yaml.exists():
        substrate = load_model(Substrate, paths.conceptual_yaml)
        existing_labels = {e.label.lower() for e in substrate.entities}

    suggestions: list[dict[str, Any]] = []
    for dataset in library.entries:
        if not dataset.columns:
            continue

        # Load the dataframe for stats (best effort).
        df = None
        if dataset.location:
            data_path = paths.root / dataset.location
            if data_path.exists():
                with suppress(Exception):
                    df = load_dataframe(data_path)

        for col in dataset.columns:
            if col.name.lower() in existing_labels:
                continue
            if col.role == "index" or col.role == "id":
                continue

            # Compute stats if dataframe is available.
            stats: dict[str, Any] | None = None
            if df is not None and col.name in df.columns:
                with suppress(Exception):
                    stats = compute_column_stats(df, col.name)

            # Infer entity kind from column dtype / role.
            kind: EntityKind = "variable" if col.dtype in ("float64", "int64") else "concept"

            description_parts: list[str] = []
            if col.description:
                description_parts.append(col.description)
            if stats:
                if stats.get("mean") is not None:
                    description_parts.append(
                        f"range [{stats['min']:.2g}, {stats['max']:.2g}], mean {stats['mean']:.2g}"
                    )
                description_parts.append(f"{stats['count']} non-null of {stats['total']}")

            suggestions.append(
                {
                    "id": f"data_{dataset.id}_{col.name}",
                    "label": col.name,
                    "kind": kind,
                    "description": "; ".join(description_parts) if description_parts else "",
                    "source": "data",
                    "sourceDetail": f"Dataset: {dataset.name}",
                    "datasetId": dataset.id,
                    "columnName": col.name,
                    "stats": {
                        "dtype": col.dtype,
                        "nonNull": int(stats["count"]) if stats else 0,
                        "unique": int(stats["unique"]) if stats else 0,
                        **(
                            {"mean": float(stats["mean"]), "min": float(stats["min"]), "max": float(stats["max"])}
                            if stats and stats.get("mean") is not None
                            else {}
                        ),
                    }
                    if stats
                    else None,
                }
            )

    return suggestions


# ---------------------------------------------------------------------------
# Edge suggestions from correlations
# ---------------------------------------------------------------------------


def suggest_edges_from_correlations(
    *,
    node_labels: list[str],
    threshold: float = 0.3,
    method: str = "pearson",
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Suggest candidate edges by computing pairwise correlations.

    Only columns whose names match an accepted node label are considered.
    Returns a list of suggestion dicts for the frontend:
    ``{id, fromLabel, toLabel, kind, source, sourceDetail, coefficient, pValue}``.
    """
    paths = require_project(root)
    if not paths.data_datasets_yaml.exists():
        return []

    library = load_model(DatasetLibrary, paths.data_datasets_yaml)
    if not library.entries:
        return []

    # Normalise node labels for case-insensitive matching.
    label_lower = {label.lower(): label for label in node_labels}

    suggestions: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for dataset in library.entries:
        # Load the dataframe.
        if not dataset.location:
            continue
        data_path = paths.root / dataset.location
        if not data_path.exists():
            continue
        try:
            df = load_dataframe(data_path)
        except Exception:
            continue

        # Find columns that match accepted node labels.
        matching_cols = [c for c in df.columns if c.lower() in label_lower]
        if len(matching_cols) < 2:
            continue

        correlations = compute_correlations(
            df,
            columns=matching_cols,
            method=method,
            threshold=threshold,
        )

        for corr in correlations:
            # Use the original node labels (preserve casing).
            label_a = label_lower.get(corr["col_a"].lower(), corr["col_a"])
            label_b = label_lower.get(corr["col_b"].lower(), corr["col_b"])

            # Deduplicate across datasets.
            pair = (min(label_a, label_b), max(label_a, label_b))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            # Direction: higher absolute correlation listed first→second.
            coeff = corr["coefficient"]
            suggestions.append(
                {
                    "id": f"corr_{dataset.id}_{corr['col_a']}_{corr['col_b']}",
                    "fromLabel": label_a,
                    "toLabel": label_b,
                    "kind": "association",
                    "source": "data",
                    "sourceDetail": f"Dataset: {dataset.name} ({method} r={coeff:+.3f})",
                    "description": (
                        f"{method.title()} correlation r={coeff:+.3f} "
                        f"(p={corr['p_value']:.4f}) between {label_a} and "
                        f"{label_b} in {dataset.name}."
                    ),
                    "coefficient": coeff,
                    "pValue": corr["p_value"],
                    "rationale": f"Correlation {coeff:+.3f} (p={corr['p_value']:.4f}) in {dataset.name}",
                    "datasetId": dataset.id,
                    "fromColumn": corr["col_a"],
                    "toColumn": corr["col_b"],
                    "statistic": method,
                    "statValue": f"r={coeff:+.4f}, p={corr['p_value']:.6f}",
                }
            )

    return suggestions


# ---------------------------------------------------------------------------
# Apply staged selections
# ---------------------------------------------------------------------------


_DESC_REQUIRED_ORIGINS = {"data-derived", "ai-proposed"}


def apply_compose_selections(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    root: Path | None = None,
) -> tuple[list[str], str, list[dict[str, str]]]:
    """Commit a batch of curated nodes and edges from the Compose workflow.

    Each node dict must have: ``label``, ``kind``, ``origin``, ``source_detail``.
    Each edge dict must have: ``from_label``, ``to_label``, ``kind``, ``origin``, ``source_detail``.

    A ``description`` field is required when ``origin`` is ``data-derived`` or
    ``ai-proposed`` (every AI/data-sourced node and edge must explain what it
    represents). Manual entries may omit it.

    Non-substrate ``kind`` values are coerced onto the canonical substrate
    kinds before anything is committed (so a stray role word like ``'driver'``
    can't hard-fail the apply); each coercion is reported.

    Optional data-provenance fields (for DataLink creation):
    - ``dataset_id``, ``column_name``, ``statistic``, ``stat_value``

    Returns ``(created_ids, commit_sha, remapped)`` where ``remapped`` is a
    list of ``{label, from, to}`` dicts describing any coerced kinds.
    """
    paths = require_project(root)

    # Validate descriptions BEFORE the batch so we don't leave a partial commit.
    missing: list[str] = []
    for node_def in nodes:
        if node_def.get("origin") in _DESC_REQUIRED_ORIGINS and not str(
            node_def.get("description", "")
        ).strip():
            missing.append(f"node {node_def.get('label', '?')!r}")
    for edge_def in edges:
        if edge_def.get("origin") in _DESC_REQUIRED_ORIGINS and not str(
            edge_def.get("description", "")
        ).strip():
            missing.append(
                f"edge {edge_def.get('from_label', '?')!r} → "
                f"{edge_def.get('to_label', '?')!r}"
            )
    if missing:
        raise ValueError(
            "Compose: description required for AI/data-sourced items: "
            + ", ".join(missing)
        )

    # Normalise kinds BEFORE the batch so a non-substrate kind (e.g. a CLD
    # role like 'driver' an LLM may emit) can never raise inside add_node and
    # hard-fail the apply. Substrate kinds are canonical; role words are
    # coerced (see schema/substrate.py). Coercions are surfaced via
    # ``remapped`` so the modeller is never silently handed a relabelled item.
    remapped: list[dict[str, str]] = []
    for node_def in nodes:
        raw = node_def.get("kind", "concept")
        new_kind, changed = coerce_entity_kind(raw)
        if changed:
            node_def["kind"] = new_kind
            remapped.append(
                {
                    "label": str(node_def.get("label", "?")),
                    "from": str(raw),
                    "to": new_kind,
                }
            )
    for edge_def in edges:
        raw = edge_def.get("kind", "causal")
        new_kind, changed = coerce_edge_kind(raw)
        if changed:
            edge_def["kind"] = new_kind
            remapped.append(
                {
                    "label": f"{edge_def.get('from_label', '?')} → "
                    f"{edge_def.get('to_label', '?')}",
                    "from": str(raw),
                    "to": new_kind,
                }
            )

    created_ids: list[str] = []
    data_links: list[DataLink] = []

    n_nodes = len(nodes)
    n_edges = len(edges)
    entity_label = "entity" if n_nodes == 1 else "entities"
    edge_label = "edge" if n_edges == 1 else "edges"
    subject = f"Compose: add {n_nodes} {entity_label}, {n_edges} {edge_label}"

    with batch(paths.root, subject=subject):
        # Create nodes first so edges can resolve them by label.
        for node_def in nodes:
            entity, _sha = add_node(
                node_def["label"],
                kind=node_def.get("kind", "concept"),
                root=paths.root,
            )
            created_ids.append(entity.id)

            desc = str(node_def.get("description", "")).strip()
            if desc:
                set_attribute(entity.id, "description", desc, root=paths.root)

            # Create DataLink for data-sourced nodes.
            if node_def.get("origin") == "data-derived" and node_def.get("dataset_id"):
                data_links.append(
                    DataLink(
                        target_id=entity.id,
                        attribute="existence",
                        dataset_id=node_def["dataset_id"],
                        column_names=[node_def["column_name"]] if node_def.get("column_name") else [],
                        statistic="column-mapping",
                        rationale=node_def.get("source_detail", ""),
                    )
                )

        for edge_def in edges:
            edge, _sha = add_edge(
                edge_def["from_label"],
                edge_def["to_label"],
                kind=edge_def.get("kind", "causal"),
                root=paths.root,
            )
            created_ids.append(edge.id)

            desc = str(edge_def.get("description", "")).strip()
            if desc:
                set_attribute(edge.id, "description", desc, root=paths.root)

            # Create DataLink for correlation-sourced edges.
            if edge_def.get("origin") == "data-derived" and edge_def.get("dataset_id"):
                cols = []
                if edge_def.get("from_column"):
                    cols.append(edge_def["from_column"])
                if edge_def.get("to_column"):
                    cols.append(edge_def["to_column"])
                data_links.append(
                    DataLink(
                        target_id=edge.id,
                        attribute="existence",
                        dataset_id=edge_def["dataset_id"],
                        column_names=cols,
                        statistic=edge_def.get("statistic", "correlation"),
                        value=edge_def.get("stat_value", ""),
                        rationale=edge_def.get("source_detail", ""),
                    )
                )

        # Persist DataLinks if any were created.
        if data_links:
            if paths.data_links_yaml.exists():
                link_set = load_model(DataLinkSet, paths.data_links_yaml)
            else:
                link_set = DataLinkSet()
            link_set.entries.extend(data_links)
            dump_model(link_set, paths.data_links_yaml)

    # The batch context manager produces the final commit SHA.
    from latris.repo import git

    sha = git.head_sha(paths.root)

    return created_ids, sha, remapped
