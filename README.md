# Sichter

Org-weite Auto-Fixes (PR-Bot, Autopilot, Hooks) für Heimgewebe-Repos.

- Service: hauski-autopilot (systemd --user)
- Konfig:  ~/sichter/autostart.env  (siehe .env.example)
- Befehle: bin/hauski-*, hooks/post-run

Quickstart:
  ./install.sh
  systemctl --user enable --now hauski-autopilot.service
