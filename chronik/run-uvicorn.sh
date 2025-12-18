#!/usr/bin/env bash
set -euo pipefail

# Resolve repo root from this script location (chronik/..)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Load secrets if available (local dev only)
if [ -f "$REPO_ROOT/secrets.env" ]; then
  # shellcheck disable=SC1090
  source "$REPO_ROOT/secrets.env"
else
  echo "No secrets.env found - continuing without it"
fi

# Allow overriding port/host/reload via env
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-1}"

ARGS=(chronik.app.main:app --host "$HOST" --port "$PORT")
if [ "$RELOAD" = "1" ]; then
  ARGS+=(--reload)
fi

echo "Starting uvicorn server..."
uv run uvicorn "${ARGS[@]}"
