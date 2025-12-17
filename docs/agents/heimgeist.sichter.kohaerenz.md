# heimgeist.sichter.kohaerenz

## Zweck
Dieser Agent produziert **Kohärenz-Befunde** aus **repoLens** Snapshots (JSON).
Er ist bewusst **kein Patch-Agent**.

Er beantwortet nur:
- Was passt zusammen?
- Was widerspricht sich?
- Wo droht Drift?

## Input
- repoLens JSON Snapshot (`repolens-agent`, `v1`, spec `2.4`)

Hinweis: Snapshots können **multi-repo** sein. Dann werden Findings pro Repo getrennt ausgewiesen.

## Output
- Markdown-Report (menschenlesbar)
- JSON-Befund (maschinenlesbar)

## Prinzipien
1. Snapshot ≠ Live-Repo
2. Beobachtung strikt getrennt von Interpretation
3. Kein "Mach das so", sondern "Das ist die Spannung"

## Heuristiken (aktuell)
- Struktur-Hinweise (pro Repo):
  - `.ai-context.yml` oder `ai-context.yml`
  - `.wgx/` (z.B. `.wgx/profile.yml`)
  - `contracts/`
  - `docs/` / `doc/`
  - `.github/workflows/`
- Meta-Checks:
  - Contract/Version/Spec
  - Coverage & Filter (Content/Path/Ext)
- Drift-Checks:
  - Stark gefilterte Snapshots (z.B. `content_policy=code-only`)
  - Duplicate Pfade **innerhalb desselben Repo** (nur dann kritisch)

## Grenzen
- Kein GitHub-Live-Zugriff
- Keine Commit-Historie
- Keine automatische Reparatur

## Aufruf (lokal)
```sh
# Standard: Markdown + JSON Report
python3 scripts/heimgeist_sichter_kohaerenz.py /path/to/repolens.json --out reports/heimgeist.sichter --json

# Mit Summary-Output für CI-Gates (einzeiliges JSON nach stdout)
python3 scripts/heimgeist_sichter_kohaerenz.py /path/to/repolens.json --out reports/heimgeist.sichter --emit-summary
```

## CI-Nutzung (GitHub Actions)
- Workflow: `.github/workflows/heimgeist-sichter-kohaerenz.yml`
- Standard: Report wird **immer** als Artifact hochgeladen (auch bei kritischen Findings).
- Gate: Nutzt `--emit-summary` für strukturierte Severity-Auswertung (kein Inline-Python).
- Fail passiert **nach** dem Artifact-Upload.
- Optional: Commit des Reports via `commit_report=true` (bewusstes Risiko).

## Robustheit
- **Technical ID konsistent:** `kohaerenz` überall als technische Kennung (ASCII-safe).
- **Unknown-Repo-Fallback:** Wenn `repo`-Feld fehlt, werden Duplicate-Findings als "warn" statt "crit" markiert
  (mit Hinweis auf fehlende Repo-Zuordnung).
- **Severity-Summary:** `--emit-summary` gibt eine JSON-Zusammenfassung aus: `max_severity`, `total_findings`, Counts je Severity.
