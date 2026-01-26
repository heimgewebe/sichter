# Plan: Sichter zum leistungsfähigen PR- & Repo-Reviewer ausbauen

> **Ziel:** Sichter soll automatisiert Fehler finden, Verbesserungen vorschlagen und qualitativ hochwertige, rauscharme Reviews liefern – lokal auf `~/repos` und remote via GitHub.

---

## Ausgangslage

**Komponentenstatus:**

- API (FastAPI): ✅ funktional (`apps/api/main.py`)
- Worker (Job-Queue): ✅ funktional (`apps/worker/run.py`)
- Dashboard (Vite/React): ✅ Grundgerüst (`apps/dashboard/`)
- LLM-Review: ⚠️ nur Placeholder (`llm_review()` in run.py)
- Statische Checks: ⚠️ shellcheck + yamllint (keine Python/JS-Checks)
- Dedupe/Themen-Bündelung: ❌ fehlt
- Caching: ❌ fehlt

**Lokale Umgebung:**

- Repos: `~/repos/<reponame>`
- Policy: `~/.config/sichter/policy.yml`
- LLM: Ollama lokal (`qwen2.5-coder:7b`) oder OpenAI remote
- GitHub CLI (`gh`) für PR-Erstellung/Zugriff

---

## Epistemische Ergänzungen (∴fore)

> **Leitgedanke:** Sichter ist kein Richter, sondern ein Wahrnehmungsfilter. Er entscheidet, ob ein Problem überhaupt die Würde eines Problems besitzt.

### A) Unsicherheitsartefakte explizit machen

**Ziel:** Risiko ≠ Unsicherheit. Unsicherheit wird als eigenes Artefakt dokumentiert.

```json
"uncertainty": {
    "level": 0.32,
    "sources": ["diff_size", "missing_context", "llm_hallucination"],
    "productive": true
}
```

**Konsequenz:**

- Unsicherheit wird im Review immer ausgewiesen.
- LLM-Ausgaben enthalten einen kurzen Unsicherheitskommentar.

### B) Findings-Typ `question`

**Ziel:** Auffälligkeiten, die nicht sicher bewertbar sind, sollen als Frage erscheinen, nicht als Urteil.

**Beispiel:**

- *„Ist das beabsichtigt, dass …?“* statt *„Das ist falsch.“*

### C) Drift ≠ Fehler

**Ziel:** Drift-Findings sind Beobachtungen, nicht Reparaturen.

**Regeln:**

- Drift-Checks niemals auto-fixen.
- Drift-PRs optional, standardmäßig deaktiviert.
- Drift bevorzugt als **Beobachtung** im Review.

### D) Provider-Provenienz im Review

**Ziel:** Wenn der LLM-Provider wechselt, wird dies transparent gemacht.

**Beispiel:**

> „Review wurde mit Provider-Wechsel erzeugt: `ollama` → `openai`“

### E) Dedupe-Key stabilisieren (mittelfristig)

**Problem:** Message-basierte Keys sind volatil.

**Ziel:** Dedupe-Key aus stabilen Quellen ableiten:

- Tool-ID + Rule-ID (z. B. ruff rule)
- AST-Anchor (Datei + Symbol)
- Normalisierte Message (ohne variable Teile)

---

## Phase 0: Fundament stabilisieren (1–2 Tage)

### 0.1 Findings-Format vereinheitlichen

**Problem:** Aktuell loggen Checks nur Text, kein strukturiertes Format.

**Maßnahme:** Einheitliches Finding-Schema einführen:

```python
# lib/findings.py
@dataclass
class Finding:
    severity: Literal["info", "warning", "error", "critical", "question"]
    category: Literal["style", "correctness", "security", "maintainability", "drift"]
    file: str
    line: int | None
    message: str
    evidence: str | None = None
    fix_available: bool = False
    dedupe_key: str = ""  # für Gruppierung
    uncertainty: dict | None = None  # z. B. {level: 0.32, sources: [...], productive: true}

    def __post_init__(self):
        if not self.dedupe_key:
            self.dedupe_key = f"{self.category}:{self.file}:{self.message[:50]}"
```

**Dateien:**

- [ ] Neu: `lib/findings.py`
- [ ] Anpassen: `apps/worker/run.py` – Checks geben `list[Finding]` zurück

### 0.2 Dedupe-Logik implementieren

**Problem:** Aktuell kann jeder Check-Lauf einen PR erzeugen → PR-Spam.

**Maßnahme:**

```python
# apps/worker/dedupe.py
def dedupe_findings(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Gruppiere Findings nach dedupe_key, behalte nur einzigartige."""
    ...

def should_create_pr(repo: str, findings: list[Finding], existing_prs: list[str]) -> bool:
    """Prüfe ob bereits ein offener PR mit diesem Thema existiert."""
    ...
```

**Dateien:**

- [ ] Neu: `apps/worker/dedupe.py`
- [ ] Anpassen: `apps/worker/run.py` – vor PR-Erstellung deduplizieren

**Dedupe-Key (Stabilisierungspfad):**

- Kurzfristig: Message-Hash + Datei (wie oben)
- Mittelfristig: Tool-ID + Rule-ID + Symbol-Anchor
- Langfristig: Semantischer Hash (AST + Normalisierung)

### 0.3 Inkrementelles Scanning (nur Changed Files)

**Problem:** `run_shellcheck()` / `run_yamllint()` scannen alle Dateien.

**Maßnahme:**

```python
def get_changed_files(repo_dir: Path, base: str = "origin/main") -> list[Path]:
    """Liefere nur geänderte Dateien seit base."""
    result = run_cmd(["git", "diff", "--name-only", base], repo_dir, check=False)
    return [repo_dir / f for f in result.stdout.splitlines() if f.strip()]
```

**Dateien:**

- [ ] Anpassen: `apps/worker/run.py` – `iter_paths()` durch `get_changed_files()` ersetzen bei `mode=changed`

---

## Phase 1: LLM-Review implementieren (3–5 Tage)

### 1.1 Provider-Abstraktion

```python
# lib/llm/provider.py
class LLMProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int = 2000) -> str: ...

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str): ...

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str): ...

def get_provider(policy: dict) -> LLMProvider:
    """Factory basierend auf policy.llm.provider"""
```

**Dateien:**

- [ ] Neu: `lib/llm/__init__.py`
- [ ] Neu: `lib/llm/provider.py`
- [ ] Neu: `lib/llm/ollama.py`
- [ ] Neu: `lib/llm/openai.py`

### 1.2 Prompt-Generator für Code-Review

```python
# lib/llm/prompts.py
def build_review_prompt(
    repo: str,
    diff: str,
    static_findings: list[Finding],
    max_suggestions: int = 3
) -> str:
    """
    Generiere fokussierten Review-Prompt.

    Output-Format (JSON):
        {
            "summary": "...",
            "risk_overall": "low|medium|high",
            "uncertainty": {
                "level": 0.0,
                "sources": ["..."],
                "productive": true
            },
            "suggestions": [
                {
                    "theme": "security",
                    "recommendation": "...",
                    "risk": "high",
                    "why": "...",
                    "files": ["path/to/file.py"]
                }
            ]
        }
    """
```

**Prompt-Design-Prinzipien:**

- Maximal 3 Vorschläge (Guardrail aus Roadmap)
- Jeder Vorschlag mit Risiko-Indikator
- Unsicherheit als eigenes Feld (nicht nur Risiko)
- Diff-fokussiert (nicht ganzer Code)
- Secrets-Redaction vor Prompt-Erstellung

**Dateien:**

- [ ] Neu: `lib/llm/prompts.py`
- [ ] Neu: `lib/llm/sanitize.py` (Secrets entfernen)

### 1.3 Review-Output parsen & speichern

```python
# lib/llm/review.py
@dataclass
class ReviewResult:
    summary: str
    risk_overall: Literal["low", "medium", "high"]
    uncertainty: dict
    suggestions: list[Suggestion]
    raw_response: str
    model: str
    provider: str
    provider_switched: bool
    tokens_used: int

def parse_review_response(raw: str) -> ReviewResult:
    """Parse JSON aus LLM-Antwort, mit Fallback."""
```

**Speicherung:** Reviews als JSONL in `~/.local/state/sichter/reviews/`

**Dateien:**

- [ ] Neu: `lib/llm/review.py`
- [ ] Anpassen: `apps/worker/run.py` – `llm_review()` implementieren

### 1.4 Token-Budget & Rate-Limiting

```yaml
# config/policy.yml Erweiterung
llm:
  provider: ollama
  model: qwen2.5-coder:7b
  base_url: http://localhost:11434
  max_tokens_per_review: 4000
  max_reviews_per_hour: 20
  fallback_provider: openai  # bei lokalen Fehlern
```

**Dateien:**

- [ ] Anpassen: `config/policy.yml`
- [ ] Neu: `lib/llm/budget.py`

---

## Phase 2: Erweiterte statische Analyse (2–3 Tage)

### 2.1 Check-Modul-Architektur

```python
# lib/checks/base.py
class Check(Protocol):
    name: str
    languages: list[str]

    def detect(self, repo_dir: Path) -> bool:
        """Ist dieser Check für das Repo relevant?"""

    def run(self, files: list[Path]) -> list[Finding]:
        """Führe Check aus, liefere Findings."""

    def autofix(self, findings: list[Finding]) -> list[Path]:
        """Optional: Wende Fixes an, liefere geänderte Dateien."""
```

### 2.2 Neue Checks implementieren

**Neue Checks (Übersicht):**

- Python Lint — `ruff` — ⭐⭐⭐ — Auto-Fix: ✅ (`ruff --fix`)
- Python Security — `bandit` — ⭐⭐ — Auto-Fix: ❌
- Python Types — `pyright` (optional) — ⭐ — Auto-Fix: ❌
- JS/TS Lint — `eslint` — ⭐⭐ — Auto-Fix: ✅ (`--fix`)
- Rust — `clippy` — ⭐ — Auto-Fix: ✅
- Markdown — `markdownlint` — ⭐ — Auto-Fix: ✅
- TOML/JSON Schema — `check-jsonschema` — ⭐ — Auto-Fix: ❌

**Dateien:**

- [ ] Neu: `lib/checks/__init__.py`
- [ ] Neu: `lib/checks/base.py`
- [ ] Neu: `lib/checks/python.py`
- [ ] Neu: `lib/checks/javascript.py`
- [ ] Neu: `lib/checks/shell.py` (refactor aus run.py)
- [ ] Neu: `lib/checks/yaml.py` (refactor aus run.py)

### 2.3 Policy-gesteuerte Check-Auswahl

```yaml
# config/policy.yml
checks:
  shellcheck: true
  yamllint: true
  python:
    ruff: true
    ruff_fix: true
    bandit: false
  javascript:
    eslint: false
  rust:
    clippy: false
```

---

## Phase 3: Heuristiken & Semantische Analyse (3–4 Tage)

### 3.1 Hotspot-Erkennung (Churn-Analyse)

```python
# lib/heuristics/hotspots.py
def analyze_churn(repo_dir: Path, days: int = 90) -> list[Hotspot]:
    """
    Finde Dateien mit hoher Änderungsfrequenz.

    git log --since="90 days ago" --name-only --format="" | sort | uniq -c | sort -rn
    """
```

**Nutzen:** Änderungen in Hotspots → höheres Risiko → prominenter in Review

### 3.2 Drift-Detektion

```python
# lib/heuristics/drift.py
def detect_version_drift(repo_dir: Path) -> list[Finding]:
    """
    Finde inkonsistente Versionen zwischen:
    - pyproject.toml vs toolchain.versions.yml
    - package.json vs package-lock.json
    - Dockerfile vs requirements.txt
    """
```

### 3.3 Redundanz-Scanner

```python
# lib/heuristics/redundancy.py
def find_similar_code(repo_dir: Path, threshold: float = 0.8) -> list[Finding]:
    """
    Finde ähnliche Code-Blöcke (Copy-Paste-Kandidaten).
    Nutze: jscpd oder einfache Hash-basierte Heuristik.
    """
```

**Dateien:**

- [ ] Neu: `lib/heuristics/__init__.py`
- [ ] Neu: `lib/heuristics/hotspots.py`
- [ ] Neu: `lib/heuristics/drift.py`
- [ ] Neu: `lib/heuristics/redundancy.py`

---

## Phase 4: Caching & Performance (1–2 Tage)

### 4.1 Ergebnis-Cache pro Commit

```python
# lib/cache.py
CACHE_DIR = Path.home() / ".cache/sichter"

def cache_key(repo: str, commit: str, check: str) -> str:
    return f"{repo}/{commit[:12]}/{check}"

def get_cached(key: str) -> list[Finding] | None: ...
def set_cached(key: str, findings: list[Finding], ttl_hours: int = 168): ...
```

**Effekt:** Wiederholte Runs auf demselben Commit überspringen bereits gelaufene Checks.

### 4.2 Parallele Repo-Verarbeitung

```python
# apps/worker/run.py
from concurrent.futures import ThreadPoolExecutor

def handle_job(job: dict) -> None:
    repos = [...]
    with ThreadPoolExecutor(max_workers=4) as pool:
        pool.map(process_single_repo, repos)
```

### 4.3 WebSocket statt Polling im Dashboard

**Status:** Bereits implementiert (`/events/stream`), aber Dashboard nutzt noch Polling.

**Maßnahme:** Dashboard auf WebSocket umstellen für Live-Updates.

---

## Phase 5: PR-Workflow verbessern (2–3 Tage)

### 5.1 Themen-Bündelung (ein PR pro Thema)

```python
# apps/worker/pr.py
def create_themed_prs(repo: str, findings: list[Finding]) -> list[str]:
    """
    Gruppiere Findings nach Thema und erstelle je einen PR:
    - sichter/style/2026-01-26
    - sichter/security/2026-01-26
    - sichter/correctness/2026-01-26
    """
```

### 5.2 PR-Beschreibung mit Review-Summary

```markdown
## Sichter Auto-Review

**Risiko-Einschätzung:** 🟡 Medium

### Zusammenfassung
Diese PR adressiert 3 Style-Findings in `lib/config.py`.

### Vorschläge
1. **Unused imports entfernen** (low risk)
   - `os` wird importiert aber nicht verwendet

2. **Type hints ergänzen** (low risk)
   - Funktion `load_yaml` hat keinen Rückgabetyp

### Betroffene Dateien

- `lib/config.py` (2 Änderungen)
```

### 5.3 Review-Kommentare statt nur PRs

```python
def add_review_comments(repo: str, pr_number: int, findings: list[Finding]) -> None:
    """Füge inline-Kommentare an betroffene Zeilen hinzu."""
    for f in findings:
        run_cmd([
            "gh", "pr", "review", str(pr_number),
            "--comment", "-b", f"**{f.severity}:** {f.message}",
            "--", f.file
        ], ...)
```

---

## Phase 6: Observability & Metriken (1–2 Tage)

### 6.1 Strukturierte Metriken

```python
# lib/metrics.py
@dataclass
class ReviewMetrics:
    repo: str
    duration_seconds: float
    findings_count: int
    findings_by_severity: dict[str, int]
    llm_tokens_used: int
    cache_hits: int
    prs_created: int
```

**Speicherung:** `insights/reviews.jsonl` (bereits vorhanden, erweitern)

### 6.2 Dashboard-Erweiterungen

- Risiko-Heatmap pro Repo
- Trend-Grafiken (Findings over time)
- Filter nach Severity/Category

---

## Implementierungsreihenfolge (empfohlen)

```text
Woche 1:
├── Phase 0.1: Finding-Format .............. [4h]
├── Phase 0.2: Dedupe-Logik ................ [4h]
├── Phase 0.3: Inkrementelles Scanning ..... [2h]
└── Phase 1.1: LLM Provider-Abstraktion .... [4h]

Woche 2:
├── Phase 1.2: Prompt-Generator ............ [6h]
├── Phase 1.3: Review-Output parsen ........ [4h]
├── Phase 1.4: Token-Budget ................ [2h]
└── Phase 2.1: Check-Modul-Architektur ..... [4h]

Woche 3:
├── Phase 2.2: Python-Checks (ruff) ........ [4h]
├── Phase 2.3: Policy-Checks ............... [2h]
├── Phase 4.1: Caching ..................... [4h]
└── Phase 5.1: Themen-PRs .................. [4h]

Woche 4:
├── Phase 3.1: Hotspot-Erkennung ........... [4h]
├── Phase 3.2: Drift-Detektion ............. [4h]
├── Phase 5.2: PR-Beschreibung ............. [2h]
└── Phase 6.1: Metriken .................... [4h]
```

---

## Quick Wins (sofort umsetzbar)

1. **Ruff aktivieren** – schnellster Python-Linter, ersetzt flake8+isort+black

    ```bash
    pip install ruff
    # In policy.yml: checks.python.ruff: true
    ```

2. **Ollama-Modell upgraden** – `qwen2.5-coder:14b` oder `deepseek-coder:6.7b` für bessere Reviews

    ```bash
    ollama pull qwen2.5-coder:14b
    ```

3. **Changed-Files-Mode als Default** – in `config/policy.yml`:

    ```yaml
    run_mode: changed  # statt "deep"
    ```

4. **gh CLI cachen** – API-Rate-Limits vermeiden:

    ```bash
    gh auth status  # prüfen
    gh cache list   # Cache-Status
    ```

---

## Offene Entscheidungen

- LLM lokal vs. remote?
  - Optionen: Ollama / OpenAI / Anthropic
  - Empfehlung: Ollama default, OpenAI fallback
- Auto-Fix automatisch committen?
  - Optionen: Ja / Nein / Nur bei low-risk
  - Empfehlung: Nur bei low-risk + Policy-Flag
- PR pro Thema oder einer für alles?
  - Optionen: Themen-PRs / Single-PR
  - Empfehlung: Themen-PRs (weniger Noise)
- Security-Findings veröffentlichen?
  - Optionen: Ja / Nein / Nur intern
  - Empfehlung: Nur intern (kein öffentlicher PR)
