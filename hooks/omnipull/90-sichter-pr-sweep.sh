#!/usr/bin/env bash
set -euo pipefail

LOG="$HOME/sichter/logs/omnipull.log"
mkdir -p "$(dirname "$LOG")"
echo "[hook 90] $(date -Is) optional pr-sweep" >> "$LOG"

if [[ "${SICHTER_EXTRA_SWEEP:-0}" != "1" ]]; then
  echo "[hook 90] skipped (SICHTER_EXTRA_SWEEP!=1)" >> "$LOG"
  exit 0
fi

MODE="${SICHTER_EXTRA_SWEEP_MODE:---all}"
{
  echo "[hook 90] run $MODE"
  "$HOME/sichter/bin/sichter-pr-sweep" "$MODE"
} >> "$LOG" 2>&1 || true
