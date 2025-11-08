#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CMD="${HOME}/bin/omnicheck"
if [ ! -x "$CMD" ]; then
 CMD="$ROOT/bin/omnicheck"
fi

if [ -x "$CMD" ]; then
 "$CMD" --changed >>"${HOME}/sichter/logs/omnipull.log" 2>&1 || true
fi
