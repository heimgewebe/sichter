#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[wgx.selftest] smoke…"
./wgx/wgx smoke

echo "[wgx.selftest] guard…"
./wgx/wgx guard

echo "[wgx.selftest] metrics… (nicht fatal, wenn nicht vorhanden)"
if ./wgx/wgx metrics; then
  echo "[wgx.selftest] metrics ok."
else
  echo "[wgx.selftest] metrics fehlgeschlagen oder nicht verfügbar." >&2
fi

echo "[wgx.selftest] alles durchlaufen."

exit 0
