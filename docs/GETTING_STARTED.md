# Getting Started mit Sichter

Diese Anleitung beschreibt die ersten Schritte nach dem Klonen des Repositories.

1. **Installationsskript ausführen**

 ```bash
 ./scripts/install.sh
 ```

 Das Skript prüft benötigte Abhängigkeiten, richtet Symlinks ein und aktiviert
 standardmäßig ausschließlich den direkten automatischen Deep-Review. Die alte
 API/Queue/Worker-Ebene bleibt deaktiviert; ein bewusstes Kompatibilitäts-Opt-in
 ist mit `SICHTER_ENABLE_LEGACY_QUEUE=1 ./scripts/install.sh` möglich.

2. **Status prüfen**

 Nach der Installation stehen folgende Befehle zur Verfügung:

 ```bash
 omnicheck --changed
 systemctl --user status sichter-autoreview.timer
 bin/sichter-pr-sweep --version
 ```

3. **Dashboard starten**

 ```bash
 SICHTER_UI_MODE=tui ./scripts/start-dashboard.sh
 ```

 Der Modus `tui` startet das interaktive Terminal-Dashboard ohne HTTP-Healthcheck.

 Für den Web-Modus:

 ```bash
 SICHTER_UI_MODE=web ./scripts/start-dashboard.sh
 curl http://127.0.0.1:5055/healthz
 ```

 Der Modus `web` startet `bin/uvicorn-app` im Hintergrund und prüft Health über
 `/healthz`. So bleiben TUI und Web-Dashboard klar getrennt.

 Web-Status und Stopp (gleiche Ownership-Logik wie beim Start):

 ```bash
 SICHTER_UI_MODE=web SICHTER_UI_ACTION=status ./scripts/start-dashboard.sh
 SICHTER_UI_MODE=web SICHTER_UI_ACTION=stop ./scripts/start-dashboard.sh
 ```

 Status und Stopp behandeln nur den getrackten Web-Prozess als eigenen Dashboard-Lifecycle.
 Fremde Listener werden sichtbar gemeldet und nur mit `SICHTER_WEB_KILL_UNKNOWN=1`
 bewusst hart beendet.

4. **WebSocket-Eventstream testen**

   ```bash
   bin/ws-selftest --base http://127.0.0.1:5055 --replay 10
   ```

   Der Test versucht zuerst eine WS-Verbindung (`/events/stream`). Falls kein WebSocket-Client
   installiert ist, fällt er auf `GET /events/recent` zurück.

 > **Hinweis:** Die Web-UI nutzt aktuell HTTP-Polling zur Aktualisierung der Event-Anzeige.
 > Eine WebSocket-basierte Echtzeit-Ansicht ist für eine spätere Version geplant.
