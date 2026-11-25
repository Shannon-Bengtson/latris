"""Telemetry config — per-project, committed, no secrets.

Lives at ``<project>/.graph-tooling/telemetry.yaml`` like ``ai_config.yaml``.
``endpoint_url`` points at the hosted telemetry service; ``upload_enabled``
is the explicit opt-in gate for anything leaving the machine. The CLI ships
no emitters for now (decision 2026-11-25), so this config mainly governs the
in-container server path and the local JSONL mirror.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from latris.repo.layout import ProjectPaths
from latris.repo.yaml_io import dump_model, load_model

CONFIG_FILENAME = "telemetry.yaml"


class TelemetryConfig(BaseModel):
    """Project-level telemetry switches."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    enabled: bool = True  # master switch for the local JSONL mirror
    upload_enabled: bool = False  # explicit opt-in: POST events to endpoint_url
    endpoint_url: str | None = None  # hosted telemetry service ingest URL


def config_path(paths: ProjectPaths) -> Path:
    return paths.state_dir / CONFIG_FILENAME


def load(paths: ProjectPaths) -> TelemetryConfig:
    """Load config for a project, returning defaults if the file doesn't exist."""
    p = config_path(paths)
    if not p.exists():
        return TelemetryConfig()
    return load_model(TelemetryConfig, p)


def save(paths: ProjectPaths, config: TelemetryConfig) -> Path:
    p = config_path(paths)
    dump_model(config, p)
    return p
