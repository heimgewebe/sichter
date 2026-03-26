"""Prompt construction for diff-focused LLM code reviews."""
from __future__ import annotations

from lib.findings import Finding
from lib.llm.sanitize import redact

# Truncate the diff at this many characters to stay inside context windows.
_MAX_DIFF_CHARS = 8_000
# Show at most this many static findings to the LLM to keep prompts concise.
_MAX_STATIC_FINDINGS = 20

_SYSTEM_BLOCK = """\
Du bist ein präziser Code-Reviewer für das Heimgewebe-Projekt.
Antworte ausschließlich mit einem gültigen JSON-Objekt (kein Markdown-Block darum).

Regeln:
- Maximal 3 konkrete, priorisierte Vorschläge.
- Jeder Vorschlag trägt ein Risiko-Label: "low" | "medium" | "high".
- Unsicherheit ist ein eigenes Artefakt – nicht unterdrücken.
- Fokus auf den Diff. Keine Stil-Nitpicks ohne klaren Sicherheits- oder Korrektheitsbezug.
- Wenn etwas unklar ist: als "question"-Typ, nicht als Urteil formulieren.

Erwartetes JSON-Format:
{
  "summary": "<2–5 Sätze Gesamteinschätzung>",
  "risk_overall": "low|medium|high",
  "uncertainty": {
    "level": 0.0,
    "sources": [],
    "productive": false
  },
  "suggestions": [
    {
      "theme": "correctness|security|style|maintainability|drift",
      "recommendation": "<konkrete Handlungsempfehlung>",
      "risk": "low|medium|high",
      "why": "<kurze Begründung mit Verweis auf Code-Stelle>",
      "files": ["pfad/zur/datei.py"]
    }
  ]
}\
"""


def build_review_prompt(
    repo: str,
    diff: str,
    static_findings: list[Finding],
    max_suggestions: int = 3,
    denylist_patterns: list[str] | None = None,
) -> str:
    """Build a diff-focused LLM review prompt.

    Secrets are redacted from the diff before inclusion.

    Args:
        repo: Repository name for context.
        diff: Raw ``git diff`` output.
        static_findings: Findings from static linters to include as context.
        max_suggestions: Number of suggestions the model should emit.

    Returns:
        Ready-to-send prompt string.
    """
    safe_diff = redact(diff, extra_patterns=denylist_patterns)
    if len(safe_diff) > _MAX_DIFF_CHARS:
        truncated = safe_diff[:_MAX_DIFF_CHARS]
        omitted = len(safe_diff) - _MAX_DIFF_CHARS
        diff_section = f"{truncated}\n\n[... Diff um {omitted} Zeichen gekürzt ...]"
    else:
        diff_section = safe_diff or "(kein Diff verfügbar)"

    findings_section = _format_static_findings(static_findings[:_MAX_STATIC_FINDINGS])

    return (
        f"{_SYSTEM_BLOCK}\n\n"
        f"--- KONTEXT ---\n"
        f"Repository: {repo}\n"
        f"Max Vorschläge: {max_suggestions}\n\n"
        f"--- DIFF ---\n"
        f"{diff_section}\n\n"
        f"--- STATISCHE ANALYSE ---\n"
        f"{findings_section or 'Keine statischen Findings.'}\n\n"
        f"Liefere jetzt das JSON-Objekt:"
    )


def _format_static_findings(findings: list[Finding]) -> str:
    lines: list[str] = []
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line is not None else f.file
        rule = f" [{f.rule_id}]" if f.rule_id else ""
        tool = f.tool or "?"
        lines.append(f"- [{f.severity}] {tool}{rule}: {f.message} ({loc})")
    return "\n".join(lines)
