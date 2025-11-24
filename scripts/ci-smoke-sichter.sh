#!/usr/bin/env bash
set -euo pipefail

# --- Konfiguration -----------------------------------------------------------
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-5055}"
API_BASE="http://${API_HOST}:${API_PORT}"
PY="${PYTHON3:-python3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sichter"
QUEUE_DIR="$STATE_DIR/queue"
EVENT_DIR="$STATE_DIR/events"
LOG_DIR="${ROOT}/.smoke-logs"
mkdir -p "$LOG_DIR" "$QUEUE_DIR" "$EVENT_DIR"

# Prozesse, die wir beenden müssen
PIDS=()
# shellcheck disable=SC2329,SC2317
cleanup() {
  set +e
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

log() { printf '[smoke] %s\n' "$*"; }

fail() {
  echo "❌ $*"
  exit 1
}

usage() {
  echo "Usage: $0 [--output PATH]"
}

# --- Argumente parsen --------------------------------------------------------
output_path=""
while (($#)); do
  case "$1" in
  --output)
    shift
    [[ $# -gt 0 ]] || {
      echo "--output braucht einen Pfad" >&2
      exit 1
    }
    output_path="$1"
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    # Unbekannte Optionen ignorieren, um die CI-Stabilität zu erhöhen
    ;;
  esac
  shift || true
done

: "${output_path:=/tmp/sichter-output.json}"

[[ -n "$output_path" ]] || {
  echo "Der Ausgabe-Pfad darf nicht leer sein" >&2
  exit 1
}
outdir="$(dirname "$output_path")"
[[ -d "$outdir" ]] || mkdir -p "$outdir"

# --- API starten -------------------------------------------------------------
log "starte API auf ${API_BASE}"
"$PY" -m uvicorn apps.api.main:app --host "$API_HOST" --port "$API_PORT" >"$LOG_DIR/api.log" 2>&1 &
PIDS+=($!)

# Warten bis /healthz antwortet
for i in {1..60}; do
  if curl -fsS "$API_BASE/healthz" >/dev/null 2>&1; then
    log "API erreichbar"
    break
  fi
  sleep 0.5
  if [[ $i -eq 60 ]]; then
    tail -n 200 "$LOG_DIR/api.log" || true
    fail "API wurde nicht rechtzeitig erreichbar"
  fi
done

# --- Worker-Stub starten -----------------------------------------------------
log "starte Worker-Stub (verarbeitet genau 1 Job)"
"$PY" "$ROOT/scripts/worker_stub.py" >"$LOG_DIR/worker.log" 2>&1 &
PIDS+=($!)

# --- Job einreihen -----------------------------------------------------------
log "enqueue job"
ENQ_JSON='{"type":"ScanChanged","mode":"changed","auto_pr":false}'
# Temp-Datei für die Server-Antwort
API_RESP=$(mktemp)
# shellcheck disable=SC2317
trap 'rm -f "$API_RESP"' EXIT
HTTP_CODE=$(curl -sS -w '%{http_code}' -o "$API_RESP" \
  -XPOST -H 'content-type: application/json' \
  "$API_BASE/jobs/submit" -d "$ENQ_JSON")

if [[ "$HTTP_CODE" -ge 200 && "$HTTP_CODE" -lt 300 ]]; then
  JID=$("$PY" -c 'import sys,json;print(json.load(sys.stdin).get("enqueued"))' <"$API_RESP")
  if [[ -n "$JID" ]]; then
    log "job id: $JID"
  else
    fail "Job-Einreihung fehlgeschlagen: Kein Job-ID in der Antwort"
  fi
else
  fail "Job-Einreihung fehlgeschlagen: HTTP-Status $HTTP_CODE, Antwort: $(cat "$API_RESP")"
fi

# --- Auf Verarbeitung warten -------------------------------------------------
log "warte auf Event-Eintrag"
SEEN=0
for i in {1..60}; do
  # wir akzeptieren sowohl /events/tail (text) als auch /events/recent (json)
  if curl -fsS "$API_BASE/events/recent?n=200" | grep -q "$JID"; then
    SEEN=1; break
  fi
  sleep 0.5
done
[[ "$SEEN" -eq 1 ]] || {
  log "Events (recent):"
  curl -fsS "$API_BASE/events/recent?n=200" || true
  tail -n 200 "$LOG_DIR/worker.log" 2>/dev/null || true
  fail "kein passendes Event zum Job gesehen"
}
log "✅ Smoke erfolgreich (Job verarbeitet und Event sichtbar)"

# --- Artefakte zeigen --------------------------------------------------------
log "Log-Auszug API:"
tail -n 60 "$LOG_DIR/api.log" || true
log "Log-Auszug Worker:"
tail -n 60 "$LOG_DIR/worker.log" || true

exit 0
