#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${HOME}/sichter/logs"
mkdir -p "$LOG_DIR"

{
 echo "[debug] $(date -Is)"
 echo " cwd: $(pwd)"
 echo " branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')"
} >>"$LOG_DIR/omnipull-debug.log"
