#!/usr/bin/env bash
set -euo pipefail
# Bootstrap-Skript für Sichter-Dev-Setup

LOG_PREFIX="[bootstrap]"
log() {
  printf "%s %s\n" "$LOG_PREFIX" "$*"
}
warn() {
  printf "%s warn: %s\n" "$LOG_PREFIX" "$*" >&2
}
die() {
  printf "%s error: %s\n" "$LOG_PREFIX" "$*" >&2
  exit 1
}

# In Repo-Root wechseln
cd "$(dirname "$0")/.."

# --- VENV ---
VENV_DIR=".venv"
REQ_FILE="requirements.txt"
LOCK_FILE="requirements.lock"

# Python-Version ermitteln
PYTHON="python"
if command -v python3 > /dev/null 2>&1; then
  PYTHON="python3"
fi
log "Nutze '$PYTHON' für Python-Aufrufe"

# Prüfen, ob venv Modul da ist
if ! "$PYTHON" -m venv --help > /dev/null 2>&1; then
  warn "Python-Modul 'venv' fehlt. Bitte nachinstallieren:"
  warn " • sudo apt install python3-venv (Debian/Ubuntu)"
  warn " • sudo dnf install python3-virtualenv (Fedora)"
  die "'venv' nicht verfügbar"
fi

# Venv erstellen/aktivieren
if [ ! -d "$VENV_DIR" ]; then
  log "Erstelle Python venv in '$VENV_DIR'"
  "$PYTHON" -m venv "$VENV_DIR"
fi
# shellcheck source=.venv/bin/activate disable=SC1091
. "$VENV_DIR/bin/activate"

# Kompatibilitätscheck für gebrochene venvs in manchen Umgebungen
if ! python -c 'import sys; sys.exit(0)' > /dev/null 2>&1; then
  warn "Venv scheint defekt. Lösche und erstelle es neu."
  rm -rf "$VENV_DIR"
  "$PYTHON" -m venv "$VENV_DIR"
  # shellcheck source=.venv/bin/activate disable=SC1091
  . .venv/bin/activate
fi

# Dependencies installieren (REQ_FILE ist optional/überschreibbar)
if command -v uv > /dev/null 2>&1; then
  log "Installiere Python-Dependencies via uv"
  if [ -f "$LOCK_FILE" ]; then
    log "Synchronisiere Python-Dependencies via uv pip sync ($LOCK_FILE)"
    uv pip sync "$LOCK_FILE"
  elif [ -f "$REQ_FILE" ]; then
    uv pip install -r "$REQ_FILE"
  else
    warn "$REQ_FILE fehlt – überspringe Python-Install"
  fi
else
  log "Installiere Python-Dependencies via pip"
  python -m pip install -U pip setuptools wheel
  if [ -f "$REQ_FILE" ]; then
    python -m pip install -r "$REQ_FILE"
  else
    warn "$REQ_FILE fehlt – überspringe Python-Install"
  fi
fi

# --- Executables (defensiv) ---
for f in bin/omnicheck bin/sichter-pr-sweep bin/sichter-dashboard bin/sweep hooks/post-run hooks/omnipull/*.sh; do
  if [ -e "$f" ]; then
    chmod +x "$f" || die "chmod +x fehlgeschlagen für $f"
  fi
done

# --- Omnipull Hook installieren ---
if compgen -G "hooks/omnipull/*.sh" > /dev/null; then
  mkdir -p "$HOME/.config/omnipull/hooks"
  for hook in hooks/omnipull/*.sh; do
    install -D -m0755 "$hook" "$HOME/.config/omnipull/hooks/$(basename "$hook")"
  done
fi

# --- systemd (user) Units deployen ---
UNIT_DIR="$HOME/.config/systemd/user"
for unit in pkg/systemd/user/*.{service,timer}; do
  [ -f "$unit" ] || continue
  install -D -m0644 "$unit" "$UNIT_DIR/$(basename "$unit")"
done

# systemd optional abschaltbar (z. B. CI/Container)
SYSTEMD_HINT=0

if [ "${BOOTSTRAP_NO_SYSTEMD:-0}" = "1" ]; then
  warn "Überspringe systemd (--user) Setup (BOOTSTRAP_NO_SYSTEMD=1)"
  SYSTEMD_HINT=1
elif ! command -v systemctl > /dev/null 2>&1; then
  warn "systemctl nicht vorhanden – überspringe systemd (--user)"
  SYSTEMD_HINT=1
else
  # Prüfen, ob systemd --user verfügbar ist (z. B. auf manchen TTYs nicht aktiv)
  if systemctl --user show-environment > /dev/null 2>&1; then
    log "systemd --user erkannt – (re)load & enable"
    systemctl --user daemon-reload
    systemctl --user enable --now sichter-api.service || warn "enable/start: sichter-api.service fehlgeschlagen"
    systemctl --user enable --now sichter-worker.service || warn "enable/start: sichter-worker.service fehlgeschlagen"
    systemctl --user enable --now sichter-autoreview.timer || warn "enable/start: sichter-autoreview.timer fehlgeschlagen"
  else
    warn "systemd --user scheint nicht aktiv. Hinweise:"
    warn " • Graphische Session nutzen ODER 'loginctl enable-linger $USER' (root) setzen,"
    warn " dann neu einloggen und erneut bootstrap ausführen."
    SYSTEMD_HINT=1
  fi
fi

echo
echo "✅ Sichter installiert."
echo "Nützliche Checks:"
echo " • curl -fsS 127.0.0.1:5055/healthz || echo 'healthz nicht erreichbar'"
echo " • systemctl --user status sichter-api.service || true"
echo " • systemctl --user status sichter-worker.service || true"
echo " • systemctl --user list-timers | grep sichter || true"
if [ "$SYSTEMD_HINT" = "1" ]; then
  echo "Tipp: sudo loginctl enable-linger $USER && neue Session starten"
fi
