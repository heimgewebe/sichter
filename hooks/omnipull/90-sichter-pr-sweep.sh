#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CMD="${HOME}/sichter/bin/sichter-pr-sweep"
if [ ! -x "$CMD" ]; then
 CMD="$ROOT/bin/sichter-pr-sweep"
fi

if [ -x "$CMD" ]; then
 "$CMD" >>"${HOME}/sichter/logs/omnipull.log" 2>&1 || true
fi
