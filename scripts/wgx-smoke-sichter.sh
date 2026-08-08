#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON3:-python3}"

if "$PY" - <<'PY' >/dev/null 2>&1
import fastapi
import pydantic
import uvicorn
import websockets
PY
then
  exec bash "$ROOT/scripts/ci-smoke-sichter.sh" "$@"
fi

base_tmp="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
venv_dir="$(mktemp -d "${base_tmp%/}/sichter-wgx-smoke.XXXXXX")"
cleanup() {
  rm -rf "$venv_dir"
}
trap cleanup EXIT INT TERM

"$PY" -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install \
  --disable-pip-version-check \
  --requirement "$ROOT/requirements.txt"
PYTHON3="$venv_dir/bin/python" bash "$ROOT/scripts/ci-smoke-sichter.sh" "$@"
