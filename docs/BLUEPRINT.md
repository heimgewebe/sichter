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
| Dashboard (Web-UI) | 🟡 | Grundgerüst: Overview, Settings, WebSocket |
| LLM-Review | ❌ | 6-Zeilen-Stub, kein LLM-Call |
| Patch-Synthese / Auto-Fix | ❌ | Kein Formatter, kein Fix-Pipeline |
| Python/JS/Security-Linter | ❌ | Nur Shell + YAML |
| Heuristiken (Hotspot/Drift) | ❌ | Nicht implementiert |
| Ergebnis-Cache | ❌ | Nicht implementiert |
| Metriken/Observability | ❌ | Nicht implementiert |

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

> Aktuell: Nur Shell + YAML. Ziel: Python, JS/TS, Security — mit Auto-Fix.

- [ ] **2.1** Check-Modul-Architektur einführen
  - [x] `lib/checks/__init__.py`
  - [x] `lib/checks/base.py` — Protocol `Check` mit `detect()`, `run()`, `autofix()`
  - [x] `lib/checks/registry.py` — Alle Checks registrieren, policy-gesteuert aktivieren
- [ ] **2.2** Bestehende Linter refactoren
  - [x] `lib/checks/shellcheck.py` — aus `run.py` extrahieren
  - [x] `lib/checks/yamllint.py` — aus `run.py` extrahieren
  - [x] Worker ruft Registry statt einzelne Funktionen auf
- [ ] **2.3** Python-Linting (ruff)
  - [x] `lib/checks/ruff.py` — `ruff check` + Output-Parsing
  - [x] Auto-Fix: `ruff check --fix` + `ruff format` (policy-gated)
  - [x] `fix_available = True` setzen bei fixbaren Findings
- [ ] **2.4** Python-Security (bandit)
  - [x] `lib/checks/bandit.py` — JSON-Output parsen
  - [x] Security-Findings als `category: "security"` taggen
  - [ ] Security-PRs optional nur intern (nicht öffentlich)
- [ ] **2.5** Shell-Auto-Fix (shfmt)
  - [x] `lib/checks/shfmt.py` — Formatierung + Diff
  - [x] Optional in Policy: `checks.shell.shfmt_fix: true`
- [ ] **2.6** JavaScript/TypeScript (eslint)
  - [x] `lib/checks/eslint.py` — nur wenn `.eslintrc`/`eslint.config.*` existiert
  - [x] Auto-Fix: `eslint --fix` (policy-gated)
- [ ] **2.7** Supply-Chain-Security (trivy)
  - [x] `lib/checks/trivy.py` — FS-Scan, JSON-Output
  - [x] Streng policy-gated, default deaktiviert
- [ ] **2.8** Auto-Fix-Pipeline verdrahten
  - [ ] Worker: Nach Linter-Run → `autofix()` aufrufen → geänderte Dateien committen
  - [ ] `fix_available`-Findings tatsächlich applizieren
  - [ ] Themen-PRs: Style-Fixes ≠ Security-Fixes ≠ Correctness-Fixes
- [ ] **2.9** Tests
  - [x] Pro Linter-Modul: Parser-Test mit Sample-Output
  - [x] Integration: Check-Registry mit Policy-Steuerung
  - [ ] Auto-Fix: Patch anwendbar, kein Dirty-State nach Revert

---

### Meilenstein 3 — Heuristiken & Semantische Analyse

> Aktuell: Keine Heuristiken. Ziel: Hotspots, Drift, Redundanz als Signalquellen.

- [ ] **3.1** Hotspot-Erkennung
  - [ ] `lib/heuristics/__init__.py`
  - [ ] `lib/heuristics/hotspots.py` — Git-Churn der letzten 90 Tage
  - [ ] Dateien mit hoher Änderungsfrequenz → erhöhtes Risiko in Review
  - [ ] Output als `Finding(category="maintainability", severity="info")`
- [ ] **3.2** Drift-Detektion
  - [ ] `lib/heuristics/drift.py` — Versionsnummern, Config-Keys vergleichen
  - [ ] Quellen: `pyproject.toml` vs `toolchain.versions.yml`, `Dockerfile` vs `requirements.txt`
  - [ ] Drift ≠ Fehler → Beobachtung, kein Auto-Fix
  - [ ] Policy-Flag: `heuristics.drift.create_pr: false` (default)
- [ ] **3.3** Redundanz-Scanner
  - [ ] `lib/heuristics/redundancy.py` — Hash-basierte Code-Block-Duplikation
  - [ ] Schwelle konfigurierbar (default: 0.8)
  - [ ] Output als Konsolidierungsvorschlag oder Rückfrage (`severity: "question"`)
- [ ] **3.4** Integration in Worker
  - [ ] Heuristiken nach Linter-Phase ausführen
  - [ ] Ergebnisse in `risk_overall` der LLM-Review einspeisen
  - [ ] Heuristik-Findings separat in Events loggen
- [ ] **3.5** Tests
  - [ ] Hotspot: Mock-Git-Log mit bekanntem Churn
  - [ ] Drift: Fixture-Repos mit absichtlicher Versionsinkonsistenz

---

### Meilenstein 4 — Caching & Performance

> Aktuell: Jeder Run prüft alles neu. Ziel: Ergebnis-Cache + parallele Verarbeitung.

- [ ] **4.1** Ergebnis-Cache
  - [ ] `lib/cache.py` — Cache-Key: `repo + commit_hash + check_name + policy_hash`
  - [ ] Speicherort: `~/.cache/sichter/`
  - [ ] TTL: 7 Tage (konfigurierbar)
  - [ ] Cache-Hit überspringt den Check komplett
- [ ] **4.2** Parallele Repo-Verarbeitung
  - [ ] `apps/worker/run.py` — `ThreadPoolExecutor` mit bounded concurrency (default: 4)
  - [ ] Jedes Repo in eigenem Thread, Thread-sichere Event-Emission
- [ ] **4.3** GitHub-Rate-Limit-Handling
  - [ ] Exponential Backoff bei 403/429 von `gh` CLI
  - [ ] Rate-Limit-Status loggen
- [ ] **4.4** Queue-Priorisierung
  - [ ] Jobs mit `priority: high` vorziehen (z.B. Security-Findings)
  - [ ] FIFO als Default beibehalten

---

### Meilenstein 5 — PR-Workflow verbessern

> Aktuell: Ein PR pro Run. Ziel: Themen-PRs, Inline-Kommentare, bessere Beschreibungen.

- [ ] **5.1** Themen-Bündelung realisieren
  - [ ] Ein Branch + PR pro Finding-Category (style, correctness, security, ...)
  - [ ] Branch-Naming: `sichter/<category>/<date>-<shortsha>`
  - [ ] Existierende PRs updaten statt neue erstellen
- [ ] **5.2** PR-Beschreibung mit Review-Summary
  - [ ] Risiko-Badge (🟢 Low / 🟡 Medium / 🔴 High)
  - [ ] Zusammenfassung (2–6 Sätze)
  - [ ] Vorschläge als nummerierte Liste mit Risiko
  - [ ] Betroffene Dateien mit Änderungszählern
  - [ ] Verifikationshinweise ("So prüfst du den Fix")
- [ ] **5.3** Inline-Review-Kommentare
  - [ ] `gh pr review --comment` an betroffenen Zeilen
  - [ ] Nur bei Findings mit konkretem `file` + `line`
  - [ ] Limit: Max 10 Inline-Kommentare pro PR
- [ ] **5.4** Security-Findings nur intern
  - [ ] Policy-Flag: `security.findings_public: false`
  - [ ] Bei `false`: Security-PRs nur als Draft oder gar nicht erstellen
  - [ ] Stattdessen: Event + interne Benachrichtigung

---

### Meilenstein 6 — Dashboard-Ausbau

> Aktuell: Overview + Settings. Ziel: Vollwertiges Sichtungscockpit.

- [ ] **6.1** Repo-Übersicht mit Findings-Heatmap
  - [ ] API: Neuer Endpoint `/repos/findings` — aggregierte Findings pro Repo
  - [ ] UI: Farbcodierte Kacheln (Grün/Gelb/Rot nach Severity)
- [ ] **6.2** Drill-Down: Repo → Dateien → Findings
  - [ ] Klick auf Repo zeigt Datei-Liste mit Finding-Counts
  - [ ] Klick auf Datei zeigt einzelne Findings mit Code-Kontext
- [ ] **6.3** Filter & Sortierung
  - [ ] Nach Severity, Category, Repo, Zeitraum
  - [ ] Suchfeld für Freitext
- [ ] **6.4** Trend-Grafiken
  - [ ] Findings over Time (letzte 30 Tage)
  - [ ] PRs erstellt/gemergt over Time
  - [ ] Review-Duration Trend
- [ ] **6.5** Job-Submit-Formular
  - [ ] Repo-Auswahl (Dropdown oder Autocomplete)
  - [ ] Modus (changed/all/deep)
  - [ ] Submit-Button → `/jobs/submit`
- [ ] **6.6** Live-Event-Feed
  - [ ] WebSocket-Stream als scrollbare Timeline
  - [ ] Event-Typ-Filter (sweep, findings, pr, error)

---

### Meilenstein 7 — Observability & Metriken

> Aktuell: JSONL-Events, kein Metrics-Export. Ziel: Messbare Qualität.

- [ ] **7.1** Strukturierte Metriken sammeln
  - [ ] `lib/metrics.py` — `ReviewMetrics`-Dataclass
  - [ ] Felder: repo, duration_seconds, findings_count, findings_by_severity, llm_tokens_used, cache_hits, prs_created
  - [ ] Speicherung in `insights/reviews.jsonl` (erweitern)
- [ ] **7.2** Metriken-API-Endpoint
  - [ ] `GET /metrics` — Aggregierte Metriken (JSON)
  - [ ] Optional: Prometheus-kompatibles Format
- [ ] **7.3** Alerts bei Anomalien
  - [ ] Plötzlicher Finding-Anstieg → Event + optionale Benachrichtigung
  - [ ] Worker-Ausfall-Erkennung (Heartbeat)
- [ ] **7.4** Review-Qualitätsmessung
  - [ ] Track: Wie viele Sichter-PRs werden gemergt vs. geschlossen?
  - [ ] False-Positive-Rate als Qualitätsindikator
  - [ ] In Dashboard als Metrik anzeigen

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
