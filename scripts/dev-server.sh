#!/usr/bin/env bash
set -euo pipefail

# scripts/dev-server.sh — Start (or restart) the Latris backend for dev.
#
# Usage:
#   bash scripts/dev-server.sh <project-root>
#   bash scripts/dev-server.sh <project-root> --port 8742
#   bash scripts/dev-server.sh <project-root> --force
#
# Idempotent: if the server is already healthy for the same project,
# this is a no-op. Use --force to restart regardless.
#
# Starts the FastAPI server with:
#   - Auto-reload on Python file changes (via watchfiles)
#   - AI mocking off by default (real AI); export LATRIS_AI_MOCK=1 to stub
#     AI responses
#   - All output logged to logs/server-<port>.log
#   - PID written to logs/server-<port>.pid

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO_ROOT/logs"

# ── Parse arguments ───────────────────────────────────────────────────
FORCE=false
PORT=8741
PROJECT_ROOT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)  FORCE=true; shift ;;
        --port)   PORT="$2"; shift 2 ;;
        --port=*) PORT="${1#*=}"; shift ;;
        *)        PROJECT_ROOT="$1"; shift ;;
    esac
done

PROJECT_ROOT="${PROJECT_ROOT:-${LATRIS_PROJECT_ROOT:-}}"
if [ -z "$PROJECT_ROOT" ]; then
    echo "Usage: bash scripts/dev-server.sh <project-root> [--port N] [--force]"
    echo "  or set LATRIS_PROJECT_ROOT env var."
    exit 1
fi
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"

LOG_FILE="$LOG_DIR/server-$PORT.log"
PID_FILE="$LOG_DIR/server-$PORT.pid"

mkdir -p "$LOG_DIR"

# ── Check if server is already running ────────────────────────────────
if ! $FORCE; then
    HEALTH=$(curl -sf "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true)
    if [ -n "$HEALTH" ]; then
        RUNNING_ROOT=$(echo "$HEALTH" | python -c "import sys,json; print(json.load(sys.stdin).get('project_root',''))" 2>/dev/null || true)
        if [ "$RUNNING_ROOT" = "$PROJECT_ROOT" ]; then
            echo "Server already running on port $PORT for this project."
            echo "Logs: $LOG_FILE"
            exit 0
        fi
        echo "WARNING: Server on port $PORT is serving a different project:"
        echo "  Running:   $RUNNING_ROOT"
        echo "  Requested: $PROJECT_ROOT"
        echo "Run with --force to restart, or use --port to pick another port."
        exit 1
    fi
fi

# ── Kill existing server ──────────────────────────────────────────────
bash "$REPO_ROOT/scripts/dev-stop.sh" --port "$PORT" 2>/dev/null || true

# ── Start fresh log ──────────────────────────────────────────────────
> "$LOG_FILE"
{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting server on port $PORT"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Project root: $PROJECT_ROOT"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Reload: enabled | AI mock: disabled (real AI)"
    echo "---"
} >> "$LOG_FILE"

# ── Start server ──────────────────────────────────────────────────────
LATRIS_PROJECT_ROOT="$PROJECT_ROOT" \
uvicorn latris.server.app:create_app \
    --factory \
    --host 127.0.0.1 \
    --port "$PORT" \
    --reload \
    --reload-dir "$REPO_ROOT/src" \
    --log-level info \
    >> "$LOG_FILE" 2>&1 &

SERVER_PID=$!
disown "$SERVER_PID" 2>/dev/null || true
echo "$SERVER_PID" > "$PID_FILE"

echo "Server started (PID $SERVER_PID) on http://127.0.0.1:$PORT"
echo "Project: $PROJECT_ROOT"
echo "Logs:    $LOG_FILE"
