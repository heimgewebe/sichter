#!/usr/bin/env bash
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SELF_DIR/../.." && pwd)"
ENVF="$ROOT/autostart.env"
LOGF="$ROOT/logs/autopilot.log"
UNIT="hauski-autopilot.service"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Fehlt: $1"; exit 1; }; }
need whiptail

_pause() { read -rp $'\n[Enter] zurück zum Menü…'; }

status_view() {
  systemctl --user status "$UNIT" --no-pager || true
  echo
  echo "--- Letzte 50 Journalzeilen ---"
  journalctl --user -u "$UNIT" -n 50 --no-pager || true
  _pause
}

restart_service() {
  systemctl --user restart "$UNIT"
  echo "Dienst neu gestartet."
  _pause
}

models_view() {
  echo "Ollama-Modelle:"
  ollama list || true
  echo
  echo "Aktuelle Backend-Config:"
  grep -E '^(HAUSKI_PR_SUGGEST_BACKEND|HAUSKI_OLLAMA_HOST|HAUSKI_OLLAMA_MODEL|HAUSKI_OLLAMA_OPTS)=' "$ENVF" || true
  _pause
}

worker_logs() {
  if [ -f "$LOGF" ]; then
    less "$LOGF"
  else
    echo "Noch kein Log vorhanden: $LOGF"
    _pause
  fi
}

trigger_fixprs() {
  if [ -x "$ROOT/hooks/post-run" ]; then
    "$ROOT/hooks/post-run" || true
  else
    echo "Hook fehlt: $ROOT/hooks/post-run"
  fi
  _pause
}

config_tuner() {
  # kleine Konfig-Maske: Intervall und Modell
  CUR_INT="$(grep -oE '^HAUSKI_WATCH_INTERVAL_SEC=.*' "$ENVF" | cut -d= -f2 || true)"
  CUR_MOD="$(grep -oE '^HAUSKI_OLLAMA_MODEL=.*' "$ENVF" | cut -d= -f2 || true)"
  NEW_INT="$(whiptail --inputbox "Watch-Intervall (Sekunden)" 10 60 "${CUR_INT:-300}" 3>&1 1>&2 2>&3 || true)"
  NEW_MOD="$(whiptail --inputbox "Ollama Modell" 10 60 "${CUR_MOD:-qwen2.5-coder:7b}" 3>&1 1>&2 2>&3 || true)"
  if [ -n "${NEW_INT:-}" ]; then
    sed -i "s/^HAUSKI_WATCH_INTERVAL_SEC=.*/HAUSKI_WATCH_INTERVAL_SEC=${NEW_INT}/" "$ENVF" || echo "HAUSKI_WATCH_INTERVAL_SEC=${NEW_INT}" >> "$ENVF"
  fi
  if [ -n "${NEW_MOD:-}" ]; then
    sed -i "s/^HAUSKI_OLLAMA_MODEL=.*/HAUSKI_OLLAMA_MODEL=${NEW_MOD}/" "$ENVF" || echo "HAUSKI_OLLAMA_MODEL=${NEW_MOD}" >> "$ENVF"
  fi
  systemctl --user restart "$UNIT"
}

menu() {
  whiptail --title "Sichter-Dashboard" --menu "Aktion wählen:" 20 72 10 \
    1 "Autopilot-Status anzeigen" \
    2 "Autopilot neu starten" \
    3 "Ollama-Modelle & Backend-Config prüfen" \
    4 "Worker-Logs (autopilot.log) ansehen" \
    5 "Fix-PRs jetzt anstoßen (post-run)" \
    6 "Config anpassen (Intervall/Modell)" \
    7 "Beenden" 3>&1 1>&2 2>&3
}

while true; do
  choice="$(menu)" || exit 0
  case "$choice" in
    1) status_view ;;
    2) restart_service ;;
    3) models_view ;;
    4) worker_logs ;;
    5) trigger_fixprs ;;
    6) config_tuner ;;
    *) exit 0 ;;
  esac
done
