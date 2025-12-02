#!/usr/bin/env bash
set -euo pipefail

LOG="$HOME/sichter/logs/omnipull.log"
mkdir -p "$(dirname "$LOG")"
{
  echo "[hook 80] $(date -Is) omnicheck --changed"
  "$HOME/sichter/bin/omnicheck" --changed
} >>"$LOG" 2>&1 || true
