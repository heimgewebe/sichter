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

## Sweep Guards

`bin/sichter-pr-sweep` läuft mit harten Schutzregeln (`hard-gates-v2`):

* Standard: `include_self_repo: false` (Self-Repo wird aus Discovery ausgeschlossen).
* Branch-Erzeugung erst nach Base-Verifikation auf `origin/main` und nur bei echten staged Änderungen.
* Bei `NOCHANGE` gilt strikt: kein Branch, kein Checkout, Reporting mit `branch=-`.
* Repo-Discovery filtert standardmäßig: `.idea`, `merges`, `exports`, `_mirror`.
* Nicht-Git-Verzeichnisse werden als `repo_skipped` markiert und nicht mutiert.

Diagnose:

```bash
bin/sichter-pr-sweep --version
```

Die Ausgabe muss `guard=hard-gates-v2` enthalten.

## Alte Autofix-Branches bereinigen

Lokale Alt-Branches prüfen:

```bash
git branch --list 'sichter/autofix-*'
```

Remote Alt-Branches prüfen:

```bash
git ls-remote --heads origin 'sichter/autofix-*'
```

Nur bewusst und manuell bereinigen (nie implizit im Sweep).
