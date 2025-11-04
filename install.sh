#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/systemd/user"
install -m 0644 "$ROOT/systemd/hauski-autopilot.service" "$HOME/.config/systemd/user/hauski-autopilot.service"
[ -f "$HOME/sichter/autostart.env" ] || cp "$ROOT/.env.example" "$HOME/sichter/autostart.env"
chmod +x "$ROOT"/bin/* "$ROOT"/hooks/* 2>/dev/null || true
echo "Install ok. Start: systemctl --user enable --now hauski-autopilot.service"
