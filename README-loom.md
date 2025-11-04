# loom — dein Arbeitsraum-Start (tmux-Wrapper)

Kurz: "loom" öffnet deinen persistenten Arbeitsraum (tmux) im aktuellen Ordner.
"loomini" ist die minimal/portable Variante (eigener tmux-Socket, ignoriert ~/.tmux.conf).

## Start

    loom         # großer Arbeitsraum mit Logs/Notes/Context
    loomini      # minimal & robust, immer im aktuellen Ordner

## Typischer Ablauf

    cd ~/repos/dein-projekt
    loom
    codex        # im oberen Pane starten

## Extras (falls im Script vorhanden)

    loom brain "Notiz …"   # hängt Zeitstempel-Notiz an codex/notes.md + Worklog
    loom save              # tmux Snapshot in ~/sichter/logs/
    loom status            # Überblick
    loom doctor            # Selbsttest
    loom edit              # codex/notes.md im Editor öffnen

## Dateien & Struktur

    <aktuelles Projekt>/
    ├─ codex/
    │  ├─ notes.md            # deine Notizen
    │  └─ context.d/          # kleine Wissens-Schnipsel (.md) fürs Projekt
    ~/sichter/
    └─ logs/                  # globale Logs (Pane/Worklog/Snapshots)

## Tipps

- Immer im Projektordner starten → Kontext stimmt für "codex".
- Falls tmux mal zickt: "loomini" nutzen (portable, eigener Socket).
- Optional: tmux-Plugins (resurrect/continuum) für Auto-Restore aktivieren.
