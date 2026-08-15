#!/usr/bin/env bash
# Starts the FastAPI backend (:8000) and Next.js dev frontend (:3000)
# together, and cleans up both on Ctrl+C. Single-command cold start —
# see README for one-time setup (.venv, npm install --prefix frontend).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

PIDS=()

cleanup() {
    echo ""
    echo "Stopping..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM

"$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
PIDS+=("$!")

npm run dev --prefix frontend &
PIDS+=("$!")

wait
