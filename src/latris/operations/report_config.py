"""Report configuration operations — load/save the persisted Communicate
report curation (selected sections, order, voice, depth, presets), one config
per model type (formalism).

See docs/design/STORY.md (Companion change) for why this moved from browser
localStorage to a git-versioned artifact.
"""

from __future__ import annotations

from pathlib import Path

from latris.operations.commit import auto_commit
from latris.repo.project import require_project
from latris.repo.yaml_io import dump_model, load_model
from latris.schema.report_config import ReportConfig, ReportConfigStore


def load_report_config_store(*, root: Path | None = None) -> ReportConfigStore:
    """Load the per-model report-config store (empty if the file is absent).

    Migrates the legacy single-config shape (one ``ReportConfig`` at the file
    root, before reports were per-formalism) into a one-entry store.
    """
    paths = require_project(root)
    path = paths.report_config_yaml
    if not path.exists():
        return ReportConfigStore()
    try:
        return load_model(ReportConfigStore, path)
    except Exception:
        # Legacy single-config file — wrap it as one (untyped) entry.
        legacy = load_model(ReportConfig, path)
        return ReportConfigStore(configs=[legacy])


def load_report_config(model_type: str, *, root: Path | None = None) -> ReportConfig:
    """Load the report config for one model type (empty defaults if unset)."""
    store = load_report_config_store(root=root)
    for config in store.configs:
        if config.model_type == model_type:
            return config
    return ReportConfig(model_type=model_type)


def save_report_config(
    config: ReportConfig,
    *,
    root: Path | None = None,
) -> tuple[ReportConfig, str]:
    """Persist one model type's report config and commit.

    The config's ``model_type`` selects which entry to replace in the store.
    Returns ``(config, commit_sha)``.
    """
    paths = require_project(root)
    store = load_report_config_store(root=root)
    store.configs = [c for c in store.configs if c.model_type != config.model_type]
    store.configs.append(config)
    dump_model(store, paths.report_config_yaml)
    sha = auto_commit(
        paths.root,
        subject=f"Update report configuration ({config.model_type or 'default'})",
        paths=[paths.report_config_yaml],
    )
    return config, sha
