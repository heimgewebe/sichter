#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_PREFIX="[install]"
log(){ printf "%s %s\n" "$LOG_PREFIX" "$*"; }
warn(){ printf "%s warn: %s\n" "$LOG_PREFIX" "$*" >&2; }
die(){ printf "%s error: %s\n" "$LOG_PREFIX" "$*" >&2; exit 1; }

need_cmd(){ command -v "$1" >/dev/null 2>&1 || die "Benötigtes Programm '$1' fehlt"; }

log "Prüfe Abhängigkeiten"
for cmd in gh git python3 pip shellcheck yamllint; do
 need_cmd "$cmd"
done

if command -v node >/dev/null 2>&1; then
 log "node gefunden: $(node --version)"
else
 warn "node nicht gefunden – Dashboard-Webbuild wird übersprungen"
fi

if command -v ollama >/dev/null 2>&1; then
 log "ollama gefunden"
else
 warn "ollama nicht gefunden – LLM Checks nutzen ggf. Remote-Anbieter"
fi

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/sichter"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_DIR/policy.yml" ]; then
 log "Kopiere Default-Policy"
 install -m0644 "$ROOT/config/policy.yml" "$CONFIG_DIR/policy.yml"
else
 log "Policy existiert bereits – überspringe Kopie"
fi

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sichter"
mkdir -p "$STATE_DIR"/queue "$STATE_DIR"/events

log "Richte Symlinks ein"
mkdir -p "$HOME/bin" "$HOME/sichter/bin"
ln -sf "$ROOT/bin/omnicheck" "$HOME/bin/omnicheck"
ln -sf "$ROOT/bin/sichter-pr-sweep" "$HOME/sichter/bin/sichter-pr-sweep"
ln -sf "$ROOT/bin/sweep" "$HOME/sichter/bin/sweep"
ln -sf "$ROOT/bin/sichter-dashboard" "$HOME/sichter/bin/sichter-dashboard"

HOOK_TARGET="${XDG_CONFIG_HOME:-$HOME/.config}/omnipull/hooks"
mkdir -p "$HOOK_TARGET"
for hook in "$ROOT"/hooks/omnipull/*.sh; do
 ln -sf "$hook" "$HOOK_TARGET/$(basename "$hook")"
done

log "Installiere systemd User-Units"
UNIT_TARGET="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_TARGET"
for unit in "$ROOT"/pkg/systemd/user/*.{service,timer}; do
 [ -f "$unit" ] || continue
 install -m0644 "$unit" "$UNIT_TARGET/$(basename "$unit")"
done

if command -v systemctl >/dev/null 2>&1; then
 if systemctl --user show-environment >/dev/null 2>&1; then
  log "Aktualisiere systemd --user"
  systemctl --user daemon-reload
  systemctl --user enable --now sichter-api.service
  systemctl --user enable --now sichter-worker.service
  systemctl --user enable --now sichter-autoreview.timer
 else
  warn "systemctl --user nicht aktiv – bitte in Session mit user systemd ausführen"
 fi
else
 warn "systemctl nicht verfügbar – systemd-Konfiguration übersprungen"
fi

LOG_DIR="$HOME/sichter/logs"
mkdir -p "$LOG_DIR"
log "Installationslog geschrieben nach $LOG_DIR"

log "Fertig"
