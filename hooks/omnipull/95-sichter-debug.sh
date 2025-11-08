#!/usr/bin/env bash
set -euo pipefail

echo "[hook 95] debug dump" >>"$HOME/sichter/logs/omnipull.log"

mkdir -p "$HOME/sichter/logs"
ENV_SNAPSHOT="$HOME/sichter/logs/omnidebug-$(date +%Y%m%d-%H%M%S).log"
{
 echo "# Environment"
 env | sort
 echo
 echo "# API health"
 if command -v curl >/dev/null 2>&1; then
 curl -fsS "${SICHTER_API_BASE:-http://127.0.0.1:8000}/healthz" || true
 echo
 curl -fsS "${SICHTER_API_BASE:-http://127.0.0.1:8000}/readyz" || true
 else
 echo "curl not available"
 fi
} >"$ENV_SNAPSHOT" 2>&1

echo "[hook 95] debug log: $ENV_SNAPSHOT"
