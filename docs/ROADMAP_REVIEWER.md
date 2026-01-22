# Roadmap: Sichter als performanter, qualitativ hochwertiger Reviewer

Dieses Dokument fasst die geplanten Ausbauschritte zusammen, um **Sichter** vom aktuellen MVP (Shell/YAML‑Lint + Auto‑PR) zu einem **modularen, vertrauenswürdigen Code‑Reviewer** mit LLM‑gestützten Reviews, Patch‑Synthese, Dedupe/Topic‑Bundling, Allow/Deny‑Policy, Performance‑Optimierungen und besserer Beobachtbarkeit weiterzuentwickeln.

## Leitprinzipien (Guardrails)

1. **Maximal drei Vorschläge pro Analyse**
   - Jede Analyse liefert höchstens **3** konkrete, priorisierte Empfehlungen.
   - Wenn mehr Findings existieren: bündeln, deduplizieren oder Rückfragen statt Liste.

2. **Jeder Vorschlag mit Risiko‑Indikator**
   - Pro Vorschlag ein Risiko‑Label (z. B. `low|medium|high`) plus kurzer Begründung.

3. **Noise reduzieren statt maximieren**
   - Ziel ist Akzeptanz: pro Thema **ein** PR, keine PR‑Stürme.

4. **Inkrementell & effizient**
   - Primär auf `git diff`/Changed‑Files arbeiten; Vollscan nur gezielt.

5. **Policy‑First**
   - Alle „mächtigen“ Features (LLM, Auto‑Fixes, Security‑Scans, Path‑Excludes) sind explizit in der Policy aktivierbar.

6. **Kohärenz‑Agent als Signalquelle**
   - Der Kohärenz‑Agent liefert Struktur/Meta/Drift‑Befunde **ohne** Reparaturvorschläge.
   - Sichter kann diese Befunde als Input in die Risiko‑Bewertung und Themen‑Bündelung einspeisen.

---

## Ausgangslage (kurz)

- Worker klont Repositories, führt aktuell Shell‑Script‑ und YAML‑Linting aus und erstellt ggf. PRs.
- Eine LLM‑basierte Review ist aktuell nur als Stub/Platzhalter vorgesehen.
- In der README sind als „nice nexts“ genannt:
  - LLM‑Analysen (Prompt + Patch‑Synthese)
  - Dashboard hinter `/` der API
  - Dedupe‑Logik (PR je Thema)
  - Reposets/Allow-/Denylist aus Policy berücksichtigen

---

## Roadmap (Phasen)

### Phase 0 — Fundament (schnell, risikoarm)

**Ziel:** Sauberes Interface für Checks + Findings + Dedupe + Policy‑Schalter, ohne sofort „große“ KI.

- Findings als einheitliches Format (Severity/Risk/Theme, file/line, summary, evidence)
- Dedupe‑Key (z. B. `theme + normalized_message + path_group`)
- Policy‑Schema erweitern: Allow/Deny‑Listen, Check‑Auswahl, LLM‑Schalter (noch optional)
- Inkrementelles Scannen konsequent: nur changed files im Default

#### Akzeptanzkriterien (Phase 0)

- Ein Run erzeugt deterministische, deduplizierte Findings.
- Keine PR‑Flut: pro Thema maximal ein PR.

### Phase 1 — LLM‑Review + Patch‑Synthese (kontrolliert)

**Ziel:** Aus Diffs und Findings eine hochwertige Review‑Zusammenfassung mit max. 3 Vorschlägen + Risiko‑Indikator generieren; optional Auto‑Fix‑Patch.

- Prompt‑Generator für LLM‑Review (Diff‑fokussiert)
- Provider‑Abstraktion (OpenAI / lokal)
- Optional: Patch‑Synthese als Branch/PR (nur wenn Policy aktiv)

#### Akzeptanzkriterien (Phase 1)

- Review‑Output erfüllt Guardrails (≤3 Vorschläge, jeder mit Risiko).
- Patch‑Synthese ist opt‑in, reproduzierbar und „fail‑safe“ (bei Fehler kein PR‑Spam).

### Phase 2 — Mehrstufige statische Analyse + Auto‑Fixes

**Ziel:** Sprachspezifische Linter/Formatter + Security‑Checks, policy‑gesteuert.

- Python: `ruff` (plus optional `bandit`)
- JS/TS: `eslint` (plus optional `prettier`)
- Shell: `shellcheck` + optional `shfmt` Auto‑Fix
- YAML: `yamllint`
- Supply‑Chain/Security: optional `trivy` (repo/FS scan) oder vergleichbare Checks

#### Akzeptanzkriterien (Phase 2)

- Pro Projekt werden nur die in der Policy erlaubten Checks ausgeführt.
- Auto‑Fixes landen in genau einem Themen‑PR.

### Phase 3 — Heuristiken als „Mini‑Checks“ (Hotspots/Drift/Redundanz)

**Ziel:** Mehr Semantik, weniger mechanische Lints.

- Hotspot‑Erkennung (Churn/Änderungsfrequenz + optional semantische Nähe)
- Drift‑Detektion (Versions-/Konfig‑Inkonsistenzen über Dateien hinweg)
- Redundanz‑Scanner (ähnliche Implementationen/duplizierte Patterns)

#### Akzeptanzkriterien (Phase 3)

- Heuristiken erhöhen die Risiko‑Signale, ohne mehr als 3 Vorschläge zu erzeugen.
- Ergebnisse sind thematisch gebündelt (strukturell/semantisch/riskant/stilistisch).

### Phase 4 — UI/Observability/Performance als Produktqualität

**Ziel:** Bedienbarkeit, Live‑Status und messbare Qualität.

- WebSocket‑Eventstream als primärer Pfad (UI nicht nur Polling)
- Risiko‑Heatmap + Filter/Drill‑Down
- Metriken: Review‑Dauer, PR‑Count, Merge‑Time, Fehlerraten
- Caching (per Commit/Tree‑Hash), parallele Repo‑Verarbeitung

---

## Konkrete Maßnahmen (umsetzungsorientiert)

### 1) LLM‑Integration: Review & Patch‑Synthese

#### 1.1 Prompt‑Generator (Review‑Text)

Input (minimiert, diff‑fokussiert):

- Repo‑Metadaten (Name, Branch, Commit)
- Changed‑Files + relevante Diff‑Hunks
- Ergebnisse der statischen Checks (nur aggregiert, nicht raw spam)
- Kohärenz‑Befunde (Struktur/Drift als Risiko‑Signal)

Output (strukturierter JSON‑Block + Markdown‑Summary):

- `summary` (2–6 Sätze)
- `risk_overall` (`low|medium|high` + Begründung)
- `suggestions[]` (max 3):
  - `theme`
  - `recommendation`
  - `risk` + `why`
  - `files[]` (wo relevant)
  - optional `questions[]` (wenn Unsicherheit)

#### 1.2 Patch‑Synthese (Auto‑Fixes)

- Nur bei `policy.llm.patch_synthesis.enabled: true`.
- Patch‑Synthese arbeitet *primär* auf den bereits identifizierten Fix‑Kandidaten (Formatter/Linter‑Fixes) und nur ergänzend generativ.
- Branch‑Naming pro Thema (`sichter/<theme>/<date>-<shortsha>`), und PR‑Text enthält:
  - Was geändert wurde
  - Risiken/Tradeoffs
  - Wie man den Fix verifiziert

#### 1.3 Provider‑Auswahl (OpenAI / lokal)

- Policy definiert Provider + Modell + Budget/Limit.
- Lokale Modelle: z. B. via HTTP‑Endpoint (Ollama/vLLM‑kompatibel) – pluggable.

#### Sicherheitsanforderungen

- Secrets‑Redaction (keine `.env`, Tokens, private keys in Prompts)
- Path‑Denylist beachten (siehe Policy unten)
- Token‑Budget begrenzen (nur hunks, nicht ganze Dateien)

---

### 2) Mehrstufige statische Analyse

#### 2.1 Policy‑gesteuerte Check‑Matrix

- Checks sind Module mit:
  - `detect()` (gilt für Repo?)
  - `run(changed_files)`
  - `autofix()` optional
  - `findings[]`

#### 2.2 Tooling‑Vorschläge

- Python: `ruff` als Default (schnell; optional `ruff format`), `bandit` optional
- JS/TS: `eslint` + optional `prettier` (nur wenn config vorhanden)
- Shell: `shellcheck`, `shfmt` Auto‑Fix optional
- Security: `trivy` optional (FS/Repo), aber streng policy‑gated

#### 2.3 Auto‑Fix‑Mechanik

- Auto‑Fixes laufen nur:
  - auf Changed‑Files
  - wenn Formatter/Tool im Repo konfiguriert ist oder in Policy explizit erzwungen wird
  - und erzeugen einen Patch, der in die Dedupe/Topic‑Bündelung einspeist

---

### 3) Heuristiken als Mini‑Checks

#### 3.1 Hotspots

- Signalquellen:
  - `git log` Churn (Commits pro Datei, Touch‑Rate)
  - optional: semantische Ähnlichkeit (z. B. ähnliche Funktionsnamen/Strukturen)
- Auswirkung:
  - erhöht `risk_overall` bei Änderungen in Hotspots

#### 3.2 Drift‑Detektion

- Beispiele:
  - Versionsnummern in mehreren Dateien (z. B. `pyproject.toml` vs `toolchain.versions.yml`)
  - Feature‑Flags/Config‑Keys in App vs Docs
- Output:
  - ein dedupliziertes Finding „Drift“ mit konkreten betroffenen Dateien

#### 3.3 Redundanz‑Scan

- Heuristik‑basiert (nicht perfekt):
  - gleiche/ähnliche Codeblöcke in mehreren Dateien
  - wiederholte Shell‑Patterns
- Output:
  - Vorschlag zur Konsolidierung (wenn Nutzen hoch, sonst Rückfrage)

---

### 4) Deduplizierung & Themen‑Bündelung

**Ziel:** Ein PR pro Thema.

- Dedupe‑Key: `theme + normalized_title + path_group`
- Themen‑Clustering:
  - `style/format`
  - `safety/security`
  - `correctness`
  - `maintainability`
  - `drift/consistency`

Wenn mehrere Checks zu einem Thema beitragen (z. B. 10 Shell‑Fixes), entsteht:

- **ein** Branch
- **ein** PR
- **ein** Review‑Block (max 3 Vorschläge)

---

### 5) Policy: Allow/Deny‑Listen & Reposets

**Ziel:** Nur relevante Repos scannen, sensible Pfade ausklammern.

Vorschlag (Schema‑Skizze; exemplarisch):

```yaml
policy:
  reposets:
    - name: core
      include_repos:
        - heimgewebe/sichter
        - heimgewebe/chronik
      exclude_repos: []

  paths:
    denylist:
      - "**/.env"
      - "**/*.key"
      - "**/secrets/**"
    allowlist: []

  llm:
    enabled: false
    provider: openai   # openai|local
    model: gpt-5.2
    max_suggestions: 3
    patch_synthesis:
      enabled: false

  checks:
    shellcheck: { enabled: true }
    yamllint:   { enabled: true }
    ruff:       { enabled: true, autofix: false }
    eslint:     { enabled: false, autofix: false }
    bandit:     { enabled: false }
    trivy:      { enabled: false }
```

Hinweis: Der konkrete Ort/Namensraum muss an die bestehende `config/policy.yml`‑Struktur angepasst werden.

---

### 6) Performance‑Optimierungen

- Inkrementell: Default‑Pfad arbeitet nur auf Changed‑Files (`--changed`).
- Caching:
  - Cache‑Key pro Commit/Tree‑Hash
  - Cache speichert Findings + Tool‑Versionen + Policy‑Hash
- Parallelisierung:
  - mehrere Repos parallel (bounded concurrency)
  - pro Repo: Tools parallel nur, wenn I/O/CPU‑Budget das zulässt
- I/O:
  - limitierte Subprocess‑Parallelität
  - optionale FS‑Trigger (inotify/watchman) für lokale Workflows

---

### 7) UI & Feedback

- Live‑Eventstream (WebSocket) zur Anzeige von:
  - Worker‑Status
  - Findings (themenbasiert)
  - PR‑Status
  - Logs
- Web‑UI Features:
  - Filter (Repo/Theme/Risk)
  - Risiko‑Heatmap
  - Drill‑Down bis File/Hunk

---

### 8) Beobachtbarkeit & Metriken

- Nutzung des vorhandenen `wgx`‑Metrik‑Snapshots als Baseline.
- Zusätzliche Metriken/Endpoints:
  - `review_duration_seconds`
  - `prs_created_total`
  - `analysis_failures_total`
  - `avg_findings_per_run` (nach Dedupe)

Optional:

- Prometheus‑Exporter / JSON‑Endpoint

---

### 9) Test‑ und Release‑Prozess

- Unit‑Tests pro neuem Check‑Modul (Parser, Dedupe‑Key, Policy‑Gate)
- Integrationstests für:
  - LLM‑Prompt‑Generator (Snapshot‑Tests)
  - Patch‑Synthese (Patch anwendbar, kein Dirty‑State)
  - End‑to‑End Worker‑Run auf Mini‑Repo
- CI:
  - `wgx smoke` und `wgx guard` in Pipeline

---

## Anhang: Review‑Output‑Kontrakt (Vorschlag)

Empfehlung: Intern konsistent als JSON, nach außen (PR‑Comment) gerendert als Markdown.

```json
{
  "summary": "...",
  "risk_overall": {"level": "medium", "why": "..."},
  "suggestions": [
    {
      "theme": "correctness",
      "recommendation": "...",
      "risk": {"level": "high", "why": "..."},
      "files": ["path/to/file.py"],
      "questions": []
    }
  ]
}
```
