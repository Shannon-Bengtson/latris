#!/usr/bin/env bash
set -euo pipefail

# scripts/dev-stop.sh — Stop the dev server.
#
# Usage:
#   bash scripts/dev-stop.sh            # stops server on default port 8741
#   bash scripts/dev-stop.sh --port 8742

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KILLED=false

# ── Parse arguments ───────────────────────────────────────────────────
PORT=8741
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)   PORT="$2"; shift 2 ;;
        --port=*) PORT="${1#*=}"; shift ;;
        *)        shift ;;
    esac
done

PID_FILE="$REPO_ROOT/logs/server-$PORT.pid"

# ── Kill by PID file ─────────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
        # Windows (Git Bash): tree-kill the process and all children.
        taskkill //F //PID "$OLD_PID" //T 2>/dev/null && KILLED=true || true
    else
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill "$OLD_PID" 2>/dev/null || true
            sleep 1
            if kill -0 "$OLD_PID" 2>/dev/null; then
                kill -9 "$OLD_PID" 2>/dev/null || true
            fi
            KILLED=true
        fi
    fi
    rm -f "$PID_FILE"
fi

# ── Fallback: kill anything still on the port ─────────────────────────
#
# A uvicorn --reload worker inherits the listening socket from its parent.
# If the parent dies first, netstat still labels the socket with the (now
# dead) parent PID, while the orphaned worker keeps serving. taskkill on the
# dead PID does nothing, so we must also hunt down children by ParentProcessId
# — which Win32_Process still resolves even when the parent is gone.
if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
    for P in $(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | sort -u); do
        if [ "$P" != "0" ]; then
            # Kill orphaned children (the inheriting reload worker) first.
            for K in $(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter 'ParentProcessId=$P').ProcessId" 2>/dev/null | tr -d '\r'); do
                taskkill //F //PID "$K" //T 2>/dev/null && KILLED=true || true
            done
            taskkill //F //PID "$P" //T 2>/dev/null && KILLED=true || true
        fi
    done
else
    for P in $(lsof -ti ":$PORT" 2>/dev/null || true); do
        kill "$P" 2>/dev/null && KILLED=true || true
    done
fi

if $KILLED; then
    echo "Server stopped."
else
    echo "No server was running."
fi
