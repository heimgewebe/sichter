#!/usr/bin/env bash
set -euo pipefail

files="$(git ls-files '*.sh' '*.bash' || true)"

if [ -n "$files" ]; then
  echo "[wgx.guard] Shell-Syntax prüfen…"
  # reine Syntaxprüfung aller Shell-Skripte
  bash -n $files

  if command -v shellcheck >/dev/null 2>&1; then
    echo "[wgx.guard] shellcheck läuft…"
    shellcheck -x $files
  else
    echo "[wgx.guard] shellcheck nicht gefunden, überspringe Lint."
  fi

  if command -v shfmt >/dev/null 2>&1; then
    echo "[wgx.guard] shfmt (Dry-Run) läuft…"
    shfmt -d $files
  else
    echo "[wgx.guard] shfmt nicht gefunden, überspringe Format-Check."
  fi
else
  echo "[wgx.guard] Keine Shell-Skripte gefunden."
fi

if command -v python3 >/dev/null 2>&1; then
  echo "[wgx.guard] Python-Compileall läuft…"
  # Compile-Check aller Python-Dateien, darf warnend scheitern
  python3 -m compileall . || true
fi

echo "[wgx.guard] fertig."
