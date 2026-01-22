# Sichter (MVP)

Autonomer Code-Reviewer + Auto-PR Engine.

## Quickstart
```bash
git clone <dieses-repo> ~/sichter
cd ~/sichter
scripts/bootstrap.sh
```
## Omnipull-Integration

Hook liegt nach `~/.config/omnipull/hooks/100-sichter-always-post.sh` und triggert nach jedem Pull:

```
~/sichter/bin/omnicheck --changed
```
## CLI
- `~/sichter/bin/omnicheck --changed|--all`
- `~/sichter/bin/sweep --changed|--all`

## Dienste
- API: `systemctl --user status sichter-api.service`
- Worker: `systemctl --user status sichter-worker.service`
- Timer: `systemctl --user list-timers | grep sichter-sweep`

## Logs
- Events/PR: `~/.local/state/sichter/events/pr.log`
- Worker:    `~/.local/state/sichter/events/worker.log`

---

## Was noch? (nice nexts)

- Roadmap: siehe [docs/ROADMAP_REVIEWER.md](docs/ROADMAP_REVIEWER.md).
- LLM-Analysen in `apps/worker/run.py` integrieren (Prompt + Patch-Synthese).
- Dashboard (Vite/React) hinter `/` der API bereitstellen.
- Dedupe-Logik erweitern (PR je Thema).
- Reposets/Allow-/Denylist aus `config/policy.yml` berücksichtigen.

## Entwicklungsumgebung

Um Shell-Skripte konsistent zu formatieren (`shfmt`), nutze das bereitgestellte Skript:

```bash
tools/scripts/ensure-shfmt.sh
```

Es lädt die korrekte Version (definiert in `toolchain.versions.yml`) nach `.local/bin/`.

## Konfiguration

- `registry.sample.json`: Entwurf für eine globale Registry (Chronik-URL, Mirror-Pfade). Aktuell nicht aktiv genutzt.
- `config/policy.yml`: Zentrale Konfiguration für Policies.

---

🧵 WGX – Mini-Einführung für Dummies

(Wie du sichter lokal prüfst, ohne zu wissen, was CI, UV oder Shell-Linting ist)

WGX ist ein kleines Werkzeug im Repo, das für dich die wichtigsten Checks ausführt.
Du musst keine Python-Umgebung bauen, keine Tools installieren und keine CI-YAMLs verstehen.

Alles läuft über ein einziges Kommando:

./wgx/wgx <task>

Es gibt vier Tasks:

---

1) 🧪 smoke – Schnelltest („geht das Repo überhaupt?“)

Was macht das?
	•	Startet die kleine API (uvicorn, FastAPI)
	•	Ruft das vorhandene Smoke-Script auf
	•	Prüft, ob sichter grob funktioniert
	•	Speichert Logs in .smoke-logs/

Ausführen:

./wgx/wgx smoke


---

2) 🛡️ guard – Fehler finden, BEVOR sie peinlich werden

Was macht das?
	•	Prüft Shell-Skripte auf Syntaxfehler
	•	Prüft Python-Dateien auf grundlegende Fehler (compileall)
	•	Nichts „Magisches“, einfach: crashed etwas, ist es falsch.

Ausführen:

./wgx/wgx guard


---

3) 📊 metrics – optionaler Metrik-Snapshot

Was macht das?
	•	Führt das vorhandene scripts/wgx-metrics-snapshot.sh aus
	•	Ergebnis landet als JSON im Repo
	•	Nur für interne Analyse gedacht

Ausführen:

./wgx/wgx metrics


---

4) 🧬 snapshot – im Repo aktuell leer

Kein Inhalt. Kann später Dinge tun (Backups, Exporte etc.).

---

Warum das gut ist
	•	Du musst keine CI verstehen – WGX fasst alles zusammen.
	•	CI läuft genau die gleichen Befehle wie du lokal.
	•	Fehler tauchen bei dir, nicht erst auf GitHub, auf.
	•	Es fühlt sich an wie ein minimales „Bau dir dein eigenes Makefile“.

---

Wenn etwas kaputt geht

Die häufigsten Gründe:

Problem	Bedeutung	Lösung
wgx: command not found	Datei nicht ausführbar	chmod +x wgx/wgx
„python3 not found“	Python fehlt	sudo apt install python3
Smoke bricht ab	API startet nicht	Logs in .smoke-logs/ anschauen
Guard bricht ab	Syntaxfehler in Shell/Python	Fixen und nochmal laufen lassen


---

Essenz

WGX ist dein Ein-Knopf-Werkzeug:
„Funktioniert das Repo?“, „gibt es offensichtliche Fehler?“ – alles mit einem einzigen Befehl.

## Organismus-Kontext

Dieses Repository ist Teil des **Heimgewebe-Organismus**.

Die übergeordnete Architektur, Achsen, Rollen und Contracts sind zentral beschrieben im  \
👉 [`metarepo/docs/heimgewebe-organismus.md`](https://github.com/heimgewebe/metarepo/blob/main/docs/heimgewebe-organismus.md)  \
👉 [`metarepo/docs/heimgewebe-zielbild.md`](https://github.com/heimgewebe/metarepo/blob/main/docs/heimgewebe-zielbild.md).

Alle Rollen-Definitionen, Datenflüsse und Contract-Zuordnungen dieses Repos
sind dort verankert.
