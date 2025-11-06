#!/usr/bin/env bash
set -euo pipefail
ts(){ date -Is; }
LOG="$HOME/sichter/logs/omnipull-sichter.log"
echo "[omnipull-hook:always] start @ $(ts)" | tee -a "$LOG"
export SICHTER_RUN_MODE="${SICHTER_RUN_MODE:-deep}"
if [[ -x "$HOME/sichter/hooks/post-run" ]]; then
  "$HOME/sichter/hooks/post-run" >>"$LOG" 2>&1 || echo "post-run warn" >>"$LOG"
fi
echo "[omnipull-hook:always] done  @ $(ts)" | tee -a "$LOG"
