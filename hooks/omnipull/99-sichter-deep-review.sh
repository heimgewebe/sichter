#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sichter"
QUEUE_DIR="$STATE_DIR/queue"
mkdir -p "$QUEUE_DIR"

job_file="$QUEUE_DIR/$(date +%s)-deep-review.json"
cat >"$job_file" <<'JSON'
{
 "type": "ScanAll",
 "mode": "all",
 "auto_pr": true
}
JSON
