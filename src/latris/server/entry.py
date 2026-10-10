"""Unified entry point for PyInstaller: server mode and init mode.

Server mode starts the FastAPI server (same as ``__main__.py``).
Init mode creates a new project and prints JSON to stdout for Electron.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _run_server(args: argparse.Namespace) -> None:
    import uvicorn

    from latris.server.app import create_app
    from latris.server.config import ServerConfig

    cfg = ServerConfig(
        project_root=args.project_root,
        host=args.host,
        port=args.port,
        reload=False,
    )
    app = create_app(project_root=cfg.project_root)
    uvicorn.run(app, host=cfg.host, port=cfg.port)


def _run_init(args: argparse.Namespace) -> None:
    from latris.operations.init import init_project

    target = Path(args.path).resolve()
    try:
        paths = init_project(
            target,
            statement=args.statement,
            name=args.name or "",
        )
        json.dump({"ok": True, "root": str(paths.root)}, sys.stdout)
    except Exception as exc:  # noqa: BLE001
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.exit(1)


def _run_list_keys() -> None:
    from latris.ai.config import DEFAULT_MODEL
    from latris.ai.credentials import list_providers

    try:
        providers = list_providers()
        # Extract provider prefix from the default model (e.g. "gemini/gemini-2.5-flash" → "gemini")
        default_provider = DEFAULT_MODEL.split("/")[0] if "/" in DEFAULT_MODEL else DEFAULT_MODEL
        json.dump(
            {"ok": True, "providers": providers, "default_provider": default_provider},
            sys.stdout,
        )
    except Exception as exc:  # noqa: BLE001
        json.dump({"ok": False, "error": str(exc), "providers": []}, sys.stdout)
        sys.exit(1)


def _run_set_key(args: argparse.Namespace) -> None:
    from latris.ai.credentials import set_key

    # Read key from stdin — no secrets in argv.
    key_value = sys.stdin.read().strip()
    if not key_value:
        json.dump({"ok": False, "error": "No key provided on stdin"}, sys.stdout)
        sys.exit(1)

    try:
        set_key(args.provider, key_value)
        json.dump({"ok": True}, sys.stdout)
    except Exception as exc:  # noqa: BLE001
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Latris backend")
    parser.add_argument(
        "--mode",
        choices=["server", "init", "list-keys", "set-key"],
        default="server",
        help="server (default), init, list-keys, or set-key",
    )

    # Server mode args
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8741)

    # Init mode args
    parser.add_argument("--path", type=str, default=None)
    parser.add_argument("--statement", type=str, default=None)
    parser.add_argument("--name", type=str, default=None)

    # set-key mode args
    parser.add_argument("--provider", type=str, default=None)

    args = parser.parse_args()

    if args.mode == "server":
        _run_server(args)
    elif args.mode == "init":
        if not args.path or not args.statement:
            parser.error("--path and --statement are required for init mode")
        _run_init(args)
    elif args.mode == "list-keys":
        _run_list_keys()
    elif args.mode == "set-key":
        if not args.provider:
            parser.error("--provider is required for set-key mode")
        _run_set_key(args)


if __name__ == "__main__":
    main()
