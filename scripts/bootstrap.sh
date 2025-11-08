#!/usr/bin/env bash
set -euo pipefail

log() { printf '[bootstrap] %s\n' "$*" >&2; }
warn() { printf '[bootstrap:warn] %s\n' "$*" >&2; }
die() { printf '[bootstrap:err] %s\n' "$*" >&2; exit 1; }

rc=0

set -E
trap 'rc=$?; warn "Abbruch in Zeile $LINENO (rc=$rc)"; exit $rc' ERR

cd "$(dirname "$0")/.."

if [ "${BOOTSTRAP_DEBUG:-0}" = "1" ]; then set -x; fi
umask 022

STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/sichter"
mkdir -p "$STATE_ROOT"/{logs,events}

REQ_FILE="${REQUIREMENTS_FILE:-requirements.txt}"
LOCK_FILE="${REQUIREMENTS_LOCK_FILE:-requirements.lock}"

# --- Python venv + deps (pref: uv, fallback: pip) ---
PY="${PYTHON3:-python3}"
command -v "$PY" >/dev/null 2>&1 || die "python3 nicht gefunden"

if [ ! -d ".venv" ] || [ ! -f ".venv/bin/activate" ]; then
  if command -v uv >/dev/null 2>&1; then
    log "Erzeuge venv mit uv"
    uv venv .venv
  else
    log "Erzeuge venv mit python3 -m venv"
    "$PY" -m venv .venv
  fi
fi

# shellcheck disable=SC1091  # Datei wird ggf. erst zur Laufzeit erzeugt
if [ ! -f ".venv/bin/activate" ]; then
  "$PY" -m venv .venv
fi
[ -f ".venv/bin/activate" ] || die "Fehler: .venv/bin/activate nicht vorhanden (defektes venv?)"
. .venv/bin/activate

# Sanity: funktioniert Python im venv?
if ! python -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
  warn "venv wirkt defekt – erstelle neu"
  rm -rf .venv
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
  else
    "$PY" -m venv .venv
  fi
  [ -f ".venv/bin/activate" ] || die "venv Re-Creation gescheitert"
  . .venv/bin/activate
fi

# Dependencies installieren (REQ_FILE ist optional/überschreibbar)
if command -v uv >/dev/null 2>&1; then
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
for f in cli/omnicheck cli/sweep hooks/omnipull/100-sichter-always-post.sh; do
  if [ -f "$f" ]; then
    chmod +x "$f" || die "chmod +x fehlgeschlagen für $f"
  else
    warn "Datei fehlt: $f (übersprungen)"
  fi
done

# --- Omnipull Hook installieren ---
if [ -f "hooks/omnipull/100-sichter-always-post.sh" ]; then
  install -D -m0755 "hooks/omnipull/100-sichter-always-post.sh" \
    "$HOME/.config/omnipull/hooks/100-sichter-always-post.sh"
fi

# --- systemd (user) Units deployen ---
UNIT_DIR="$HOME/.config/systemd/user"
for unit in sichter-api.service sichter-worker.service sichter-sweep.service sichter-sweep.timer; do
  if [ -f "pkg/systemd/$unit" ]; then
    install -D -m0644 "pkg/systemd/$unit" "$UNIT_DIR/$unit"
  else
    warn "systemd unit file not found: pkg/systemd/$unit"
  fi
done

# systemd optional abschaltbar (z. B. CI/Container)
SYSTEMD_HINT=0

if [ "${BOOTSTRAP_NO_SYSTEMD:-0}" = "1" ]; then
  warn "Überspringe systemd (--user) Setup (BOOTSTRAP_NO_SYSTEMD=1)"
  SYSTEMD_HINT=1
elif ! command -v systemctl >/dev/null 2>&1; then
  warn "systemctl nicht vorhanden – überspringe systemd (--user)"
  SYSTEMD_HINT=1
else
  # Prüfen, ob systemd --user verfügbar ist (z. B. auf manchen TTYs nicht aktiv)
  if systemctl --user show-environment >/dev/null 2>&1; then
    log "systemd --user erkannt – (re)load & enable"
    systemctl --user daemon-reload
    # enable + now; Fehler nicht verschlucken, sondern melden
    systemctl --user enable --now sichter-api.service    || warn "enable/start: sichter-api.service fehlgeschlagen"
    systemctl --user enable --now sichter-worker.service || warn "enable/start: sichter-worker.service fehlgeschlagen"
    systemctl --user enable --now sichter-sweep.timer    || warn "enable/start: sichter-sweep.timer fehlgeschlagen"
  else
    warn "systemd --user scheint nicht aktiv. Hinweise:"
    warn "  • Graphische Session nutzen ODER 'loginctl enable-linger $USER' (root) setzen,"
    warn "    dann neu einloggen und erneut bootstrap ausführen."
    SYSTEMD_HINT=1
  fi
fi

echo
echo "✅ Sichter installiert."
echo "Nützliche Checks:"
echo "  • curl -fsS 127.0.0.1:5055/healthz || echo 'healthz nicht erreichbar'"
echo "  • systemctl --user status sichter-api.service    || true"
echo "  • systemctl --user status sichter-worker.service || true"
echo "  • systemctl --user list-timers | grep sichter    || true"
if [ "$SYSTEMD_HINT" = "1" ]; then
  echo "Tipp: sudo loginctl enable-linger $USER && neue Session starten"
fi
