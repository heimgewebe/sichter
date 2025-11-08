# Getting Started mit Sichter

Diese Anleitung beschreibt die ersten Schritte nach dem Klonen des Repositories.

1. **Installationsskript ausführen**

 ```bash
 ./scripts/install.sh
 ```

 Das Skript prüft benötigte Abhängigkeiten, richtet Symlinks ein und aktiviert die
 systemd-Units für API, Worker und den automatischen Deep-Review.

2. **Status prüfen**

 Nach der Installation stehen folgende Befehle zur Verfügung:

 ```bash
 omnicheck --changed
 systemctl --user status sichter-api.service
 systemctl --user status sichter-worker.service
 ```

3. **Dashboard starten**

 ```bash
 sichter-dashboard
 ```

 Der Befehl startet die TUI-Variante des Dashboards. Sobald die Web-UI verfügbar ist,
 öffnet der gleiche Befehl diese Version.
