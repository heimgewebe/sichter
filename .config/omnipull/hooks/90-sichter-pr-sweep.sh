#!/usr/bin/env bash
set -euo pipefail
# nur laufen, wenn Policy an
. "$HOME/.config/sichter/policy.env" 2>/dev/null || true
[[ "${SICHTER_SWEEP_ON_OMNIPULL:-1}" != "1" ]] && exit 0
MODE="--changed"
exec "$HOME/sichter/bin/sichter-pr-sweep" "$MODE"
