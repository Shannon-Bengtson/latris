"""Server configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    """Runtime configuration for the API server."""

    project_root: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8741
    reload: bool = field(default=False)
