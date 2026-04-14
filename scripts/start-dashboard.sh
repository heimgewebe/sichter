#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UI_MODE="${SICHTER_UI_MODE:-web}"
UI_ACTION="${1:-${SICHTER_UI_ACTION:-start}}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5055}"

WEB_BIN_DEFAULT="$ROOT_DIR/bin/uvicorn-app"
TUI_BIN_DEFAULT="$ROOT_DIR/bin/sichter-dashboard"
WEB_BIN="${SICHTER_DASHBOARD_WEB_BIN:-$WEB_BIN_DEFAULT}"
TUI_BIN="${SICHTER_DASHBOARD_TUI_BIN:-$TUI_BIN_DEFAULT}"

HEALTH_PATH="${SICHTER_HEALTH_PATH:-/healthz}"
HEALTH_URL="${SICHTER_HEALTH_URL:-http://${HOST}:${PORT}${HEALTH_PATH}}"
HEALTH_TIMEOUT_SECONDS="${SICHTER_HEALTH_TIMEOUT_SECONDS:-20}"
HEALTH_INTERVAL_SECONDS="${SICHTER_HEALTH_INTERVAL_SECONDS:-1}"
WEB_KILL_PORT="${SICHTER_WEB_KILL_PORT:-$PORT}"
RUN_DIR="${SICHTER_RUN_DIR:-$ROOT_DIR/.run}"
WEB_PID_FILE="${SICHTER_WEB_PID_FILE:-$RUN_DIR/web-dashboard.pid}"
WEB_KILL_UNKNOWN="${SICHTER_WEB_KILL_UNKNOWN:-0}"
WEB_STDOUT="${SICHTER_WEB_STDOUT:-/dev/null}"
WEB_STDERR="${SICHTER_WEB_STDERR:-/dev/null}"

log() {
  printf '[start-dashboard] %s\n' "$*"
}

die() {
  printf '[start-dashboard] ERROR: %s\n' "$*" >&2
  exit 1
}

require_executable() {
  local bin_path="$1"
  local label="$2"
  if [[ ! -x "$bin_path" ]]; then
    die "${label} binary not executable: $bin_path"
  fi
}

listeners_on_port() {
  local port="$1"
  [[ -z "$port" ]] && return 0
  command -v lsof >/dev/null 2>&1 || return 0
  lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true
}

kill_tracked_web_process_if_needed() {
  local port="$1"
  [[ -f "$WEB_PID_FILE" ]] || return 1

  local tracked_pid
  tracked_pid="$(cat "$WEB_PID_FILE" 2>/dev/null || true)"
  [[ "$tracked_pid" =~ ^[0-9]+$ ]] || {
    rm -f "$WEB_PID_FILE"
    return 1
  }

  if ! kill -0 "$tracked_pid" >/dev/null 2>&1; then
    rm -f "$WEB_PID_FILE"
    return 1
  fi

  local listeners
  listeners="$(listeners_on_port "$port")"
  if [[ " $listeners " == *" $tracked_pid "* ]]; then
    log "Stopping tracked web process pid=$tracked_pid on port $port"
    kill "$tracked_pid" >/dev/null 2>&1 || true
    wait "$tracked_pid" 2>/dev/null || true
    rm -f "$WEB_PID_FILE"
    return 0
  fi

  return 1
}

stop_web_dashboard() {
  local listeners
  listeners="$(listeners_on_port "$WEB_KILL_PORT")"

  if kill_tracked_web_process_if_needed "$WEB_KILL_PORT"; then
    return 0
  fi

  [[ -z "$listeners" ]] && {
    log "No tracked web dashboard process running"
    return 0
  }

  if [[ "$WEB_KILL_UNKNOWN" == "1" ]]; then
    log "Force-stopping unknown listener(s) on port $WEB_KILL_PORT: $listeners"
    kill $listeners >/dev/null 2>&1 || true
    return 0
  fi

  die "Port $WEB_KILL_PORT is in use by unknown PID(s): $listeners (set SICHTER_WEB_KILL_UNKNOWN=1 to force stop)"
}

status_web_dashboard() {
  local listeners
  listeners="$(listeners_on_port "$WEB_KILL_PORT")"

  if [[ -f "$WEB_PID_FILE" ]]; then
    local tracked_pid
    tracked_pid="$(cat "$WEB_PID_FILE" 2>/dev/null || true)"
    if [[ "$tracked_pid" =~ ^[0-9]+$ ]] && [[ " $listeners " == *" $tracked_pid "* ]]; then
      log "Web dashboard is running (pid=$tracked_pid, port=$WEB_KILL_PORT)"
      return 0
    fi

    if [[ ! "$tracked_pid" =~ ^[0-9]+$ ]] || ! kill -0 "$tracked_pid" >/dev/null 2>&1; then
      rm -f "$WEB_PID_FILE"
    fi
  fi

  if [[ -n "$listeners" ]]; then
    log "Port $WEB_KILL_PORT is used by unknown listener(s): $listeners"
    return 1
  fi

  log "Web dashboard is not running"
  return 1
}

ensure_port_available_for_web() {
  local port="$1"
  local listeners
  listeners="$(listeners_on_port "$port")"
  [[ -z "$listeners" ]] && return 0

  if [[ "$WEB_KILL_UNKNOWN" == "1" ]]; then
    log "Force-stopping unknown listener(s) on port $port: $listeners"
    kill $listeners >/dev/null 2>&1 || true
    return 0
  fi

  die "Port $port is already in use by PID(s): $listeners (refusing to kill unknown listeners; set SICHTER_WEB_KILL_UNKNOWN=1 to force)"
}

wait_for_health() {
  local url="$1"
  local timeout="$2"
  local interval="$3"

  local elapsed=0
  while (( elapsed < timeout )); do
    local remaining=$((timeout - elapsed))
    local connect_timeout=1

    if (( remaining < connect_timeout )); then
      connect_timeout=$remaining
    fi

    if curl -fsS \
      --connect-timeout "$connect_timeout" \
      --max-time "$remaining" \
      "$url" >/dev/null 2>&1; then
      log "Health check passed: $url"
      return 0
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done

  return 1
}

case "$UI_MODE" in
  web)
    mkdir -p "$RUN_DIR"
    case "$UI_ACTION" in
      start)
        require_executable "$WEB_BIN" "web"
        command -v curl >/dev/null 2>&1 || die "curl is required in web mode"

        kill_tracked_web_process_if_needed "$WEB_KILL_PORT" || true
        ensure_port_available_for_web "$WEB_KILL_PORT"

        log "Starting web dashboard via $WEB_BIN"
        # Detach web process stdio from caller to avoid inherited-FD hangs.
        "$WEB_BIN" </dev/null >>"$WEB_STDOUT" 2>>"$WEB_STDERR" &
        web_pid=$!
        printf '%s\n' "$web_pid" >"$WEB_PID_FILE"

        if ! wait_for_health "$HEALTH_URL" "$HEALTH_TIMEOUT_SECONDS" "$HEALTH_INTERVAL_SECONDS"; then
          kill "$web_pid" >/dev/null 2>&1 || true
          wait "$web_pid" 2>/dev/null || true
          rm -f "$WEB_PID_FILE"
          die "Web dashboard failed health check: $HEALTH_URL"
        fi

        log "Web dashboard running (pid=$web_pid)"
        ;;
      stop)
        stop_web_dashboard
        ;;
      status)
        status_web_dashboard
        ;;
      *)
        die "Invalid SICHTER_UI_ACTION='$UI_ACTION' (expected: start|stop|status)"
        ;;
    esac
    ;;
  tui)
    [[ "$UI_ACTION" == "start" ]] || die "Action '$UI_ACTION' is only supported for web mode"
    require_executable "$TUI_BIN" "tui"
    log "Starting TUI dashboard via $TUI_BIN"
    exec "$TUI_BIN"
    ;;
  *)
    die "Invalid SICHTER_UI_MODE='$UI_MODE' (expected: web|tui)"
    ;;
esac
