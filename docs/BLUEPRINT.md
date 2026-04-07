# Blaupause: Sichter zum mächtigen Repo- & PR-Sichtungstool ausbauen

> **Stand:** 2026-03-25 — automatisch eruiert aus Codebase, Roadmap & Plan  
> **Zweck:** Abhakbare Roadmap, die wir Schritt für Schritt abarbeiten

---

## Legende

- ✅ = bereits implementiert und getestet
- 🟡 = Ansatz vorhanden, aber unvollständig
- ❌ = fehlt komplett (Stub oder gar nicht angelegt)

---

## IST-Zustand (Zusammenfassung)

| Komponente | Status | Wo |
| --- | --- | --- |
| Finding-Datenmodell | ✅ | `lib/findings.py` |
| Shellcheck-Linting | ✅ | `apps/worker/run.py` |
| Yamllint-Linting | ✅ | `apps/worker/run.py` |
| Deduplizierung | ✅ | `apps/worker/dedupe.py` |
| Changed-Files-Modus | ✅ | `apps/worker/run.py` → `get_changed_files()` |
| Job-Queue + Worker | ✅ | `apps/worker/run.py`, JSON-Queue |
| REST-API (FastAPI) | ✅ | `apps/api/main.py` — Auth, Events, Jobs, Policy |
| WebSocket-Events | ✅ | API + Dashboard-Hook mit Fallback auf Polling |
| PR-Erstellung | ✅ | Branching, Push, `gh pr create` |
| PR-Kommentare/Suggests | ✅ | `hauski-pr-suggest`, `hauski-pr-bot` |
| Policy-System | ✅ | YAML, Fallback-Kette, API-editierbar |
| Systemd-Integration | ✅ | API + Worker als User-Services |
| Dashboard (Web-UI) | 🟡 | Grundgerüst: Overview, Settings, Repos, WebSocket |
| LLM-Review | ✅ | `lib/llm/*`, `apps/worker/run.py` |
| Patch-Synthese / Auto-Fix | 🟡 | `lib/checks/*`, Worker-Autofix + Commit-Pfad |
| Python/JS/Security-Linter | 🟡 | `lib/checks/ruff.py`, `bandit.py`, `eslint.py`, `trivy.py` |
| Heuristiken (Hotspot/Drift/Redundanz) | 🟡 | `lib/heuristics/*.py`, Worker-Integration + Tests |
| Ergebnis-Cache | ✅ | `lib/cache.py`, `apps/worker/run.py` |
| Metriken/Observability | 🟡 | `lib/metrics.py`, `/metrics`, `/metrics/raw` |

---

## Roadmap

### Meilenstein 0 — Fundament abrunden

> Phase 0 ist zu 90% fertig. Es fehlen kleine Lücken.

- [x] Finding-Dataclass mit severity, category, dedupe_key, uncertainty
- [x] Deduplizierung (`dedupe_findings`, `should_create_pr`)
- [x] Inkrementelles Scanning (`get_changed_files`)
- [x] Policy-Fallback (User → Repo → Defaults)
- [x] Shellcheck-Integration mit Exclude-Support
- [x] Yamllint-Integration
- [x] Event-Logging (JSONL)
- [x] **0.1** Dedupe-Key stabilisieren: Tool-ID + Rule-ID statt Message-Hash
  - Datei: `lib/findings.py` — `__post_init__` erweitern
  - Datei: `apps/worker/run.py` — `tool` und `rule_id` konsequent setzen
- [x] **0.2** Uncertainty-Felder tatsächlich befüllen (aktuell immer `None`)
- [x] **0.3** Themen-Bündelung: ein PR pro Category statt ein PR für alles
  - Datei: Neue Funktion `create_themed_prs()` in `apps/worker/run.py`
  - Branch-Naming: `sichter/<category>/<date>`

---

### Meilenstein 1 — LLM-Review (der größte Hebel)

> Aktuell: ✅ Vollständig implementiert — Meilenstein 1 abgeschlossen.

- [x] **1.1** Provider-Abstraktion anlegen
  - [x] `lib/llm/__init__.py`
  - [x] `lib/llm/provider.py` — Protocol-Klasse `LLMProvider` mit `complete(prompt) → str`
  - [x] `lib/llm/ollama.py` — HTTP-Client für Ollama (`/api/generate`)
  - [x] `lib/llm/openai.py` — OpenAI-kompatible API (auch für lokale vLLM-Endpoints)
  - [x] `lib/llm/factory.py` — `get_provider(policy)` Factory-Funktion
- [x] **1.2** Prompt-Generator
  - [x] `lib/llm/prompts.py` — Diff-fokussierter Review-Prompt
  - [x] Max 3 Vorschläge pro Review (Guardrail im Prompt)
  - [x] Risiko-Indikator pro Vorschlag fordern
  - [x] Uncertainty als eigenes Feld
  - [x] Kontext: Repo-Meta + Diff-Hunks + aggregierte Static-Findings
- [x] **1.3** Secrets-Schutz vor Prompt-Erstellung
  - [x] `lib/llm/sanitize.py` — `.env`, Tokens, Keys aus Diff entfernen
  - [x] Denylist-Patterns aus Policy respektieren
- [x] **1.4** Review-Output parsen
  - [x] `lib/llm/review.py` — JSON-Parsing mit robustem Fallback
  - [x] `ReviewResult`-Dataclass: summary, risk_overall, suggestions[], uncertainty
  - [x] Provider-Provenienz im Output (Modell + Provider + ob gewechselt)
- [x] **1.5** Token-Budget & Rate-Limiting
  - [x] `lib/llm/budget.py` — `max_tokens_per_review`, `max_reviews_per_hour`
  - [x] Policy-Erweiterung für Budget-Konfiguration
  - [x] Fallback-Provider bei lokalen Fehlern
- [x] **1.6** Integration in Worker-Pipeline
  - [x] `apps/worker/run.py` — `llm_review()` mit echten LLM-Calls ersetzen
  - [x] Review-Ergebnisse als JSONL speichern (`~/.local/state/sichter/reviews/`)
  - [x] Review-Summary in PR-Beschreibung / PR-Kommentar einbetten
- [x] **1.7** Tests
  - [x] Unit-Test für Prompt-Generator (Truncation + Redaction)
  - [x] Unit-Test für Response-Parser (gültiges + kaputtes JSON, Markdown-Block)
  - [x] Mock-Test für Provider-Abstraktion (factory, Ollama, OpenAI)

---

### Meilenstein 2 — Erweiterte Linter & Auto-Fix

> Aktuell: 🟡 Erweiterte Checks und erste Autofixes sind implementiert; E2E-Autofix-Feinschliff bleibt offen.

- [x] **2.1** Check-Modul-Architektur einführen
  - [x] `lib/checks/__init__.py`
  - [x] `lib/checks/base.py` — Protocol `Check` mit `detect()`, `run()`, `autofix()`
  - [x] `lib/checks/registry.py` — Alle Checks registrieren, policy-gesteuert aktivieren
- [x] **2.2** Bestehende Linter refactoren
  - [x] `lib/checks/shellcheck.py` — aus `run.py` extrahieren
  - [x] `lib/checks/yamllint.py` — aus `run.py` extrahieren
  - [x] Worker ruft Registry statt einzelne Funktionen auf
- [x] **2.3** Python-Linting (ruff)
  - [x] `lib/checks/ruff.py` — `ruff check` + Output-Parsing
  - [x] Auto-Fix: `ruff check --fix` + `ruff format` (policy-gated)
  - [x] `fix_available = True` setzen bei fixbaren Findings
- [x] **2.4** Python-Security (bandit)
  - [x] `lib/checks/bandit.py` — JSON-Output parsen
  - [x] Security-Findings als `category: "security"` taggen
  - [x] Security-PRs optional nur intern: `security.findings_public: false` → Draft
- [x] **2.5** Shell-Auto-Fix (shfmt)
  - [x] `lib/checks/shfmt.py` — Formatierung + Diff
  - [x] Optional in Policy: `checks.shell.shfmt_fix: true`
- [x] **2.6** JavaScript/TypeScript (eslint)
  - [x] `lib/checks/eslint.py` — nur wenn `.eslintrc`/`eslint.config.*` existiert
  - [x] Auto-Fix: `eslint --fix` (policy-gated)
- [x] **2.7** Supply-Chain-Security (trivy)
  - [x] `lib/checks/trivy.py` — FS-Scan, JSON-Output
  - [x] Streng policy-gated, default deaktiviert
- [x] **2.8** Auto-Fix-Pipeline verdrahten
  - [x] Worker: Nach Linter-Run → `autofix()` aufrufen → geänderte Dateien committen
  - [x] `fix_available`-Findings tatsächlich applizieren
  - [x] Themen-PRs: Style-Fixes ≠ Security-Fixes ≠ Correctness-Fixes (`create_themed_prs`)
- [x] **2.9** Tests
  - [x] Pro Linter-Modul: Parser-Test mit Sample-Output
  - [x] Integration: Check-Registry mit Policy-Steuerung
  - [x] Auto-Fix: Patch anwendbar, kein Dirty-State nach Revert

---

### Meilenstein 3 — Heuristiken & Semantische Analyse

> Aktuell: 🟡 Kern-Heuristiken sind implementiert; Feinschliff und Ausbau bleiben offen.

- [x] **3.1** Hotspot-Erkennung
  - [x] `lib/heuristics/__init__.py`
  - [x] `lib/heuristics/hotspots.py` — Git-Churn der letzten 90 Tage
  - [x] Dateien mit hoher Änderungsfrequenz → erhöhtes Risiko in Review
  - [x] Output als `Finding(category="maintainability", severity="info")`
- [x] **3.2** Drift-Detektion
  - [x] `lib/heuristics/drift.py` — Versionsnummern zwischen `pyproject.toml` und `requirements.txt`
  - [x] Weitere Quellen: `toolchain.versions.yml` ↔ `Dockerfile` ARG/ENV-Pins
  - [x] Drift ≠ Fehler → Beobachtung, kein Auto-Fix
  - [x] Policy-Flag: `checks.drift.create_pr: false` (default)
- [x] **3.3** Redundanz-Scanner
  - [x] `lib/heuristics/redundancy.py` — Hash-basierte Code-Block-Duplikation
  - [x] Schwelle konfigurierbar
  - [x] Output als Konsolidierungsvorschlag oder Rückfrage (`severity: "question"`)
- [x] **3.4** Integration in Worker
  - [x] Heuristiken nach Linter-Phase ausführen
  - [x] Ergebnisse fließen als zusätzliche Findings in die LLM-Review ein
  - [x] Heuristik-Findings separat in Events loggen
- [x] **3.5** Tests
  - [x] Hotspot: Mock-Git-Log mit bekanntem Churn
  - [x] Drift: Fixture-Repos mit absichtlicher Versionsinkonsistenz
  - [x] Redundanz: Duplikat- und Grenzfall-Tests

---

### Meilenstein 4 — Caching & Performance

> Aktuell: 🟡 Ergebnis-Cache, Parallelisierung, GitHub-Backoff und Queue-Priorisierung sind da.

- [x] **4.1** Ergebnis-Cache
  - [x] `lib/cache.py` — Cache-Key: `repo + commit_hash + check_name + policy_hash`
  - [x] Speicherort: `~/.cache/sichter/`
  - [x] TTL: 7 Tage (aktuell Default im Code)
  - [x] Cache-Hit überspringt den Check komplett
- [x] **4.2** Parallele Repo-Verarbeitung
  - [x] `apps/worker/run.py` — `ThreadPoolExecutor` mit bounded concurrency
  - [x] Jedes Repo in eigenem Thread, Fehler werden pro Repo als Event geloggt
- [x] **4.3** GitHub-Rate-Limit-Handling
  - [x] Exponential Backoff bei erkannten Rate-Limit-Fehlern von `gh` CLI
  - [x] Rate-Limit-Status loggen
- [x] **4.4** Queue-Priorisierung
  - [x] Jobs mit `priority: high` vorziehen (z.B. Security-Findings)
  - [x] FIFO als Default beibehalten

---

### Meilenstein 5 — PR-Workflow verbessern

> Aktuell: 🟡 Themen-PRs, Inline-Kommentare und Review-Summary sind angelegt; Feinschliff bleibt offen.

- [x] **5.1** Themen-Bündelung realisieren
  - [x] Ein Branch + PR pro Finding-Category (style, correctness, security, ...)
  - [x] Branch-Naming: `sichter/<category>/<date>-<shortsha>`
  - [x] Existierende PRs updaten statt neue erstellen
- [x] **5.2** PR-Beschreibung mit Review-Summary
  - [x] Risiko-Badge (🟢 Low / 🟡 Medium / 🔴 High)
  - [x] Zusammenfassung (2–6 Sätze)
  - [x] Vorschläge als nummerierte Liste mit Risiko
  - [x] Betroffene Dateien mit Änderungszählern (Top-10-Tabelle)
  - [x] Verifikationshinweise ("So prüfst du den Fix") per Category
- [x] **5.3** Inline-Review-Kommentare
  - [x] `gh pr review --comment` an betroffenen Zeilen
  - [x] Nur bei Findings mit konkretem `file` + `line`
  - [x] Limit: Max 10 Inline-Kommentare pro PR
- [x] **5.4** Security-Findings nur intern
  - [x] Policy-Flag: `security.findings_public: false`
  - [x] Bei `false`: Security-PRs als Draft erstellen
  - [x] Security-PRs vollständig unterdrücken via `security.suppress_pr: true`
  - [x] Stattdessen: `security_findings_suppressed`-Event + interne Benachrichtigung

---

### Meilenstein 6 — Dashboard-Ausbau

> Aktuell: Overview + Settings + Repos-Grundseite. Ziel: Vollwertiges Sichtungscockpit.

- [x] **6.1** Repo-Übersicht mit Findings-Heatmap
  - [x] API: Neuer Endpoint `/repos/findings` — letzter Findings-Snapshot pro Repo aus Metrics
  - [x] UI-Basisanschluss: Repos-Tabelle zeigt `findingsCount` und `topSeverity` mit Farbpunkt
  - [x] UI-Heatmap: Farbcodierte Kacheln (Grün/Gelb/Rot nach Severity) + Table-/Heatmap-Toggle
- [x] **6.2** Drill-Down: Repo → Dateien → Findings
  - [x] Klick auf Repo öffnet Drill-Down-Panel mit Datei-Liste + Finding-Counts
  - [x] Klick auf Datei filtert einzelne Findings mit Severity + Category
  - [x] API: `/repos/findings/detail?repo=X` liefert `files` und `items`
- 🟡 **6.3** Filter & Sortierung
  - [x] Severity-Filter + Category-Filter im Drill-Down
  - [x] Suchfeld für Repo-Namen in der Übersicht
  - [x] Multi-Key-Sort (Name / Findings / Severity, asc/desc)
- [x] **6.4** Trend-Grafiken
  - [x] Findings over Time (7/14/30/90 Tage) — `/metrics/trends`
  - [x] Eigenständige Metrics-Seite mit CSS-Balkendiagramm
- [x] **6.5** Job-Submit-Formular
  - [x] Repo-Auswahl mit Autocomplete (`<datalist>` aus `/repos/status`)
  - [x] Modus-Auswahl (changed/all)
  - [x] Submit-Button → `/api/jobs/submit`
- [x] **6.6** Live-Event-Feed
  - [x] WebSocket-Stream als scrollbare Timeline (Overview-Seite)
  - [x] Event-Typ-Filter (all/sweep/findings/pr/error/llm_review/autofix/heuristics)

---

### Meilenstein 7 — Observability & Metriken

> Aktuell: 🟡 Metrik-Erfassung und API sind vorhanden; Alerts und Qualitätsauswertung fehlen.

- [x] **7.1** Strukturierte Metriken sammeln
  - [x] `lib/metrics.py` — `ReviewMetrics`-Dataclass
  - [x] Felder: repo, duration_seconds, findings_count, findings_by_severity, llm_tokens_used, cache_hits, prs_created
  - [x] Speicherung in `insights/reviews.jsonl`
- [x] **7.2** Metriken-API-Endpoint
  - [x] `GET /metrics` — Aggregierte Metriken (JSON)
  - [x] `GET /metrics/trends` — Tages-Zeitreihe (JSON)
  - [x] `GET /metrics/prometheus` — Prometheus-kompatibles Exposition-Format
- [x] **7.3** Alerts bei Anomalien
  - [x] `GET /alerts` — Spike-Erkennung via `detect_anomalies()` (rolling window ×2.5)
  - [x] Dashboard-Anomalie-Banner in Overview-Seite
  - [x] Heartbeat via WebSocket (`heartbeat`-Events)
- [x] **7.4** Review-Qualitätsmessung
  - [x] `GET /metrics/review-quality` — Cache-Effizienz, PR-Yield, Token-Effizienz
  - [x] Severity-Verteilung in Prozent
  - [x] Top-Repos nach kumulativen Findings
  - [x] Dashboard-Sektion "Review-Qualität" in Metrics-Seite

---

## Abhängigkeitsgraph

```text
Meilenstein 0 (Fundament)
    │
    ├──→ Meilenstein 1 (LLM-Review)
    │        │
    │        └──→ Meilenstein 5 (PR-Workflow)
    │                 │
    │                 └──→ Meilenstein 7 (Metriken)
    │
    ├──→ Meilenstein 2 (Linter & Auto-Fix)
    │        │
    │        ├──→ Meilenstein 3 (Heuristiken)
    │        │
    │        └──→ Meilenstein 4 (Caching)
    │
    └──→ Meilenstein 6 (Dashboard)
```

**Empfohlene Reihenfolge:** 0 → 1 → 2 → 5 → 4 → 3 → 6 → 7

Meilenstein 1 (LLM) hat den größten Impact. Meilenstein 2 (Linter) macht Auto-Fix erst möglich. Meilenstein 5 (PR-Workflow) baut auf beiden auf. Dashboard und Metriken können parallel laufen, sind aber weniger dringend.

---

## Offene Entscheidungen (vor Meilenstein 1 klären)

| # | Frage | Optionen | Empfehlung |
| --- | --- | --- | --- |
| D1 | LLM-Provider-Default? | Ollama lokal / OpenAI remote / beides | Ollama default, OpenAI fallback |
| D2 | Auto-Fix automatisch committen? | Immer / Nie / Nur bei low-risk | Nur bei low-risk + Policy-Flag |
| D3 | Ein PR oder Themen-PRs? | Single-PR / Pro Category | Themen-PRs (weniger Noise) |
| D4 | Security-Findings veröffentlichen? | Öffentlich / Nur Draft / Nur intern | Nur intern |
| D5 | Max Review-Vorschläge? | 3 / 5 / unbegrenzt | 3 (Guardrail) |
| D6 | Welches Ollama-Modell? | qwen2.5-coder:7b / 14b / deepseek-coder | 14b wenn RAM reicht |

---

## Quick Wins (sofort machbar, ohne Architekturänderung)

- [x] **Q1** ruff als Check hinzufügen (analog zu shellcheck/yamllint in `run.py`)
- [x] **Q2** `tool` und `rule_id` bei bestehenden Checks konsequent setzen
- [x] **Q3** Dedupe-Key auf `tool:rule_id:file` umstellen
- [x] **Q4** PR-Beschreibung um Finding-Summary ergänzen (Markdown-Template)
- [x] **Q5** `shfmt` als optionalen Auto-Fixer für Shell-Scripts einbauen

---

## Dateien & Verzeichnisse (zu erstellen)

```text
lib/
├── llm/                    # Meilenstein 1
│   ├── __init__.py
│   ├── provider.py         # Protocol + Base
│   ├── ollama.py           # Ollama-Client
│   ├── openai.py           # OpenAI-Client
│   ├── factory.py          # Provider-Factory
│   ├── prompts.py          # Prompt-Generator
│   ├── review.py           # Response-Parser + ReviewResult
│   ├── sanitize.py         # Secrets-Redaction
│   └── budget.py           # Token-Budget
├── checks/                 # Meilenstein 2
│   ├── __init__.py
│   ├── base.py             # Check-Protocol
│   ├── registry.py         # Check-Registry
│   ├── shellcheck.py       # Refactor aus run.py
│   ├── yamllint.py         # Refactor aus run.py
│   ├── ruff.py             # Python
│   ├── bandit.py           # Python Security
│   ├── shfmt.py            # Shell Auto-Fix
│   ├── eslint.py           # JS/TS
│   └── trivy.py            # Supply-Chain
├── heuristics/             # Meilenstein 3
│   ├── __init__.py
│   ├── hotspots.py
│   ├── drift.py
│   └── redundancy.py
├── cache.py                # Meilenstein 4
└── metrics.py              # Meilenstein 7
```
