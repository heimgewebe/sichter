# Betriebsleitfaden

## Logs & Events

* Laufzeit-Logs werden unter `~/sichter/logs/` abgelegt.
* Ereignisse landen als JSONL-Dateien in `~/.local/state/sichter/events/`.

## Dienste

Alle systemd User-Units befinden sich unter `~/.config/systemd/user/` und werden
über `systemctl --user` gesteuert.

* `sichter-autoreview.timer` — kanonischer periodischer Deep-Review über `bin/sichter-pr-sweep --all`
* `sichter-api.service` — deaktivierte Legacy-REST-API für Queue und Einstellungen
* `sichter-worker.service` — deaktivierter Legacy-Queue-Worker
* `sichter-ws-selftest.timer` — deaktivierter Legacy-API-Selbsttest

Installations- und Bootstrap-Pfade aktivieren standardmäßig nur den direkten
Review-Timer. Die Legacy-Ebene darf ausschließlich bewusst mit
`SICHTER_ENABLE_LEGACY_QUEUE=1` aktiviert werden. Sie ist keine zweite
Produktions- oder Aufgabenwahrheit.

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
