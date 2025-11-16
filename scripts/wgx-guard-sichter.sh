#!/usr/bin/env bash
set -euo pipefail

echo "[wgx.guard] Sammle Shell-Skripte…"

files=()

# 1) Skripte mit üblicher Endung
while IFS= read -r -d '' f; do
  files+=( "$f" )
done < <(git ls-files -z -- '*.sh' '*.bash' 2>/dev/null || true)

# 2) Extensionless Skripte anhand Shebang erkennen
while IFS= read -r -d '' f; do
  if [ -f "$f" ] && head -n1 "$f" | grep -qE '^#!.*(bash|sh)'; then
    files+=( "$f" )
  fi
done < <(git ls-files -z 2>/dev/null || true)

# 3) Duplikate entfernen
if ((${#files[@]} > 0)); then
  declare -A seen=()
  unique=()
  for f in "${files[@]}"; do
    if [[ -z "${seen["$f"]+x}" ]]; then
      seen["$f"]=1
      unique+=( "$f" )
    fi
  done
  files=( "${unique[@]}" )
fi

if ((${#files[@]} == 0)); then
  echo "[wgx.guard] Keine Shell-Skripte gefunden."
else
  echo "[wgx.guard] Prüfe folgende Shell-Skripte:"
  printf '  %s\n' "${files[@]}"

  echo "[wgx.guard] Shell-Syntax prüfen…"
  bash -n "${files[@]}"

  if command -v shellcheck >/dev/null 2>&1; then
    echo "[wgx.guard] shellcheck läuft…"
    shellcheck -x "${files[@]}"
  else
    echo "[wgx.guard] shellcheck nicht gefunden, überspringe Lint."
  fi

  if command -v shfmt >/dev/null 2>&1; then
    echo "[wgx.guard] shfmt (Dry-Run) läuft…"
    shfmt -d "${files[@]}"
  else
    echo "[wgx.guard] shfmt nicht gefunden, überspringe Format-Check."
  fi
fi

if command -v ruff >/dev/null 2>&1; then
  echo "[wgx.guard] ruff läuft…"
  ruff check .
else
  echo "[wgx.guard] ruff nicht gefunden, überspringe Python-Lint."
fi

if command -v python3 >/dev/null 2>&1; then
  echo "[wgx.guard] Python-Compileall läuft…"
  # Compile-Check aller Python-Dateien, darf warnend scheitern
  python3 -m compileall . || true
fi

echo "[wgx.guard] fertig."
