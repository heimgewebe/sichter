#!/usr/bin/env bash
set -euo pipefail
: "${REVIEW_ROOT:=$HOME/sichter/review}"
export REVIEW_ROOT
exec "$(dirname "$0")/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8765 --log-level info
