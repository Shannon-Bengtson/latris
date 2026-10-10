"""Entry point: ``python -m latris.server``."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

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

    app = create_app(project_root=cfg.project_root)
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
