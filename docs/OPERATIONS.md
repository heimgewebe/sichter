# Betriebsleitfaden

## Logs & Events

* Laufzeit-Logs werden unter `~/sichter/logs/` abgelegt.
* Ereignisse landen als JSONL-Dateien in `~/.local/state/sichter/events/`.

## Dienste

Alle systemd User-Units befinden sich unter `~/.config/systemd/user/` und werden
über `systemctl --user` gesteuert.

* `sichter-api.service` — REST-API für Queue und Einstellungen
* `sichter-worker.service` — autonomer Worker für Linting und Auto-PRs
* `sichter-autoreview.timer` — periodischer Deep-Review

## Hooks

Die Omnipull-Hooks werden als Symlinks nach `~/.config/omnipull/hooks/` installiert
und orchestrieren Omnicheck-Läufe sowie Auto-PR-Sweeps.
