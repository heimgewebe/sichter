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

require_command() {
  local command_name="$1"
  local reason="$2"
  command -v "$command_name" >/dev/null 2>&1 || die "$command_name is required for $reason"
}

require_web_lifecycle_prereqs() {
  require_command lsof "web dashboard port checks"
}

listeners_on_port() {
  local port="$1"
  [[ -z "$port" ]] && return 0
  lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true
}

write_web_pid_metadata() {
  local pid="$1"
  local web_bin="$2"
  local file="$3"
  # Store: pid, started_at (Unix timestamp), and the basename of web binary.
  # Format: pid|started_at|cmd_basename
  local started_at
  started_at="$(date +%s)"
  printf '%s|%s|%s\n' "$pid" "$started_at" "$(basename "$web_bin")" >"$file"
}

verify_tracked_pid_identity() {
  local file="$1"
  local web_bin="$2"
  # Read metadata and verify:
  # 1. PID is numeric and alive
  # 2. Process command line contains web_bin basename (not exact match, allows wrappers)
  # 3. Start time metadata exists (additional ownership hint)
  
  [[ -f "$file" ]] || return 1
  
  local metadata
  metadata="$(cat "$file" 2>/dev/null || true)"
  [[ -n "$metadata" ]] || return 1
  
  local tracked_pid started_at cmd_basename
  # Parse metadata: pid|started_at|cmd_basename
  tracked_pid="${metadata%%|*}"
  started_at="${metadata#*|}"
  started_at="${started_at%%|*}"
  cmd_basename="${metadata##*|}"
  
  # PID must be numeric
  [[ "$tracked_pid" =~ ^[0-9]+$ ]] || return 1
  
  # PID must be alive
  if ! kill -0 "$tracked_pid" >/dev/null 2>&1; then
    return 1
  fi
  
  # Verify start_at is numeric (metadata integrity check)
  [[ "$started_at" =~ ^[0-9]+$ ]] || return 1
  
  # Verify process command line contains expected web_bin basename.
  # This prevents killing an unrelated reused PID.
  local proc_cmd
  proc_cmd="$(ps -p "$tracked_pid" -o args= 2>/dev/null || true)"
  [[ "$proc_cmd" == *"$(basename "$web_bin")"* ]] || return 1
  
  echo "$tracked_pid"
  return 0
}

kill_tracked_web_process_if_needed() {
  local port="$1"
  local web_bin="$2"
  
  local tracked_pid
  tracked_pid="$(verify_tracked_pid_identity "$WEB_PID_FILE" "$web_bin" 2>/dev/null || true)"
  [[ -n "$tracked_pid" ]] || {
    rm -f "$WEB_PID_FILE"
    return 1
  }
  
  local listeners
  listeners="$(listeners_on_port "$port")"
  if [[ " $listeners " == *" $tracked_pid "* ]]; then
    log "Stopping tracked web process pid=$tracked_pid on port $port (listener matched)"
  else
    log "Stopping tracked web process pid=$tracked_pid (alive but not listening on port $port)"
  fi
  
  kill "$tracked_pid" >/dev/null 2>&1 || true
  wait "$tracked_pid" 2>/dev/null || true
  rm -f "$WEB_PID_FILE"
  return 0
}

stop_web_dashboard() {
  local listeners
  listeners="$(listeners_on_port "$WEB_KILL_PORT")"

  if kill_tracked_web_process_if_needed "$WEB_KILL_PORT" "$WEB_BIN"; then
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
  # State machine: check tracked ownership first, then port listeners.
  # Return: 0 = running and tracked, 1 = not running, 2 = unknown listener
  
  local tracked_pid
  tracked_pid="$(verify_tracked_pid_identity "$WEB_PID_FILE" "$WEB_BIN" 2>/dev/null || true)"
  
  local listeners
  listeners="$(listeners_on_port "$WEB_KILL_PORT")"
  
  # Tracked process is valid and listening: running state, exit 0
  if [[ -n "$tracked_pid" ]] && [[ " $listeners " == *" $tracked_pid "* ]]; then
    log "Web dashboard is running (pid=$tracked_pid, port=$WEB_KILL_PORT)"
    return 0
  fi
  
  # Tracked process exists but is detached from port: clear stale ownership
  if [[ -n "$tracked_pid" ]]; then
    log "Tracked web process pid=$tracked_pid is alive but detached from port $WEB_KILL_PORT; clearing ownership state"
    rm -f "$WEB_PID_FILE"
  elif [[ -f "$WEB_PID_FILE" ]]; then
    # PID file exists but identity verification failed: stale or invalid metadata
    rm -f "$WEB_PID_FILE"
  fi
  
  # Unknown listener on port: exit 2 (distinct from "not running")
  if [[ -n "$listeners" ]]; then
    log "Port $WEB_KILL_PORT is used by unknown listener(s): $listeners"
    return 2
  fi
  
  # Port is clean and no tracked process: not running, exit 1
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
    require_web_lifecycle_prereqs
    mkdir -p "$RUN_DIR"
    case "$UI_ACTION" in
      start)
        require_executable "$WEB_BIN" "web"
        command -v curl >/dev/null 2>&1 || die "curl is required in web mode"

        kill_tracked_web_process_if_needed "$WEB_KILL_PORT" "$WEB_BIN" || true
        ensure_port_available_for_web "$WEB_KILL_PORT"

        log "Starting web dashboard via $WEB_BIN"
        # Detach web process stdio from caller to avoid inherited-FD hangs.
        "$WEB_BIN" </dev/null >>"$WEB_STDOUT" 2>>"$WEB_STDERR" &
        web_pid=$!
        write_web_pid_metadata "$web_pid" "$WEB_BIN" "$WEB_PID_FILE"

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
