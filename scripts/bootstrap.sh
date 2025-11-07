#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Python venv + deps
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# Executables
chmod +x cli/omnicheck cli/sweep hooks/omnipull/100-sichter-always-post.sh

# Hook nach ~/.config/omnipull/hooks/
mkdir -p "$HOME/.config/omnipull/hooks"
install -m0755 hooks/omnipull/100-sichter-always-post.sh "$HOME/.config/omnipull/hooks/100-sichter-always-post.sh"

# systemd (user)
mkdir -p "$HOME/.config/systemd/user"
install -m0644 pkg/systemd/sichter-api.service    "$HOME/.config/systemd/user/"
install -m0644 pkg/systemd/sichter-worker.service "$HOME/.config/systemd/user/"
install -m0644 pkg/systemd/sichter-sweep.service  "$HOME/.config/systemd/user/"
install -m0644 pkg/systemd/sichter-sweep.timer    "$HOME/.config/systemd/user/"

systemctl --user daemon-reload
systemctl --user enable --now sichter-api.service
systemctl --user enable --now sichter-worker.service
systemctl --user enable --now sichter-sweep.timer || true

echo "✅ Sichter installiert. Test:"
echo "  • curl -s 127.0.0.1:5055/healthz"
echo "  • $HOME/sichter/cli/omnicheck --all"
echo "Logs: ~/.local/state/sichter/{events,logs}"
