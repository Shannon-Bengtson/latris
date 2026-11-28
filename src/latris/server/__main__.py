"""Entry point: ``python -m latris.server``."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from latris.server.access import warn_if_exposed
from latris.server.app import create_app
from latris.server.config import ServerConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="latris API server")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Explicit project directory (default: discover from cwd)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8741)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    cfg = ServerConfig(
        project_root=args.project_root,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )

    warn_if_exposed(cfg.host)
    if cfg.reload:
        # Reloading needs the app as an import string: uvicorn re-imports it in a fresh process,
        # which finds the project through the env var create_app reads.
        if cfg.project_root is not None:
            os.environ["LATRIS_PROJECT_ROOT"] = str(cfg.project_root)
        uvicorn.run("latris.server.app:create_app", factory=True, host=cfg.host, port=cfg.port, reload=True)
        return
    app = create_app(project_root=cfg.project_root)
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
