#!/usr/bin/env bash
set -euo pipefail

LOG="$HOME/sichter/logs/omnipull.log"
mkdir -p "$(dirname "$LOG")"
echo "[hook 99] $(date -Is) deep review sweep" >> "$LOG"

if [[ "${SICHTER_DEEP_REVIEW:-1}" != "1" ]]; then
  echo "[hook 99] skipped (SICHTER_DEEP_REVIEW!=1)" >> "$LOG"
  exit 0
fi

{
  echo "[hook 99] run ${SICHTER_DEEP_REVIEW_MODE:---changed} (deep)"
  SICHTER_RUN_MODE=deep "$HOME/sichter/bin/sichter-pr-sweep" "${SICHTER_DEEP_REVIEW_MODE:---changed}"
} >> "$LOG" 2>&1 || true
