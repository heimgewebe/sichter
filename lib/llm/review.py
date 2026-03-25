"""LLM response parsing and ReviewResult dataclass."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal


RiskLevel = Literal["low", "medium", "high"]
_VALID_RISKS = {"low", "medium", "high"}


@dataclass
class Suggestion:
    theme: str
    recommendation: str
    risk: RiskLevel
    why: str
    files: list[str] = field(default_factory=list)


@dataclass
class ReviewResult:
    summary: str
    risk_overall: RiskLevel
    uncertainty: dict
    suggestions: list[Suggestion]
    raw_response: str
    model: str = ""
    provider: str = ""
    provider_switched: bool = False
    tokens_used: int = 0

    def to_pr_section(self) -> str:
        """Render the review as a Markdown section for PR bodies."""
        risk_badge = {"low": "🟢 Low", "medium": "🟡 Medium", "high": "🔴 High"}.get(
            self.risk_overall, self.risk_overall
        )
        lines: list[str] = [
            "### LLM-Review",
            "",
            f"**Risiko-Einschätzung:** {risk_badge}",
            "",
            f"**Zusammenfassung:** {self.summary}",
        ]

        if self.suggestions:
            lines.extend(["", "**Vorschläge:**", ""])
            for i, s in enumerate(self.suggestions, 1):
                risk_label = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(s.risk, "")
                lines.append(f"{i}. {risk_label} **{s.theme}** — {s.recommendation}")
                if s.why:
                    lines.append(f"   - Begründung: {s.why}")
                if s.files:
                    lines.append(f"   - Dateien: {', '.join(s.files)}")

        unc = self.uncertainty
        if unc and unc.get("level", 0) > 0:
            lines.extend(["", f"*Unsicherheit: {unc.get('level', 0):.0%}*"])

        if self.provider and self.model:
            lines.extend(["", f"*Modell: {self.provider}/{self.model}*"])

        return "\n".join(lines)


def parse_review_response(
    raw: str,
    model: str = "",
    provider: str = "",
    tokens_used: int = 0,
) -> ReviewResult:
    """Parse JSON from LLM response with a plain-text fallback.

    Args:
        raw: Raw text response from the LLM.
        model: Model name for provenance tracking.
        provider: Provider name for provenance tracking.
        tokens_used: Token count reported by the provider.

    Returns:
        Parsed ``ReviewResult``.
    """
    json_str = _extract_json_block(raw)

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _fallback_result(raw, model, provider, tokens_used)

    if not isinstance(data, dict):
        return _fallback_result(raw, model, provider, tokens_used)

    risk_overall = str(data.get("risk_overall", "medium")).lower()
    if risk_overall not in _VALID_RISKS:
        risk_overall = "medium"

    suggestions: list[Suggestion] = []
    for s in (data.get("suggestions") or [])[:3]:
        if not isinstance(s, dict):
            continue
        risk = str(s.get("risk", "medium")).lower()
        if risk not in _VALID_RISKS:
            risk = "medium"
        suggestions.append(
            Suggestion(
                theme=str(s.get("theme", "correctness")),
                recommendation=str(s.get("recommendation", "")),
                risk=risk,  # type: ignore[arg-type]
                why=str(s.get("why", "")),
                files=[str(f) for f in (s.get("files") or [])],
            )
        )

    return ReviewResult(
        summary=str(data.get("summary", "")).strip(),
        risk_overall=risk_overall,  # type: ignore[arg-type]
        uncertainty=data.get("uncertainty") if isinstance(data.get("uncertainty"), dict) else {},
        suggestions=suggestions,
        raw_response=raw,
        model=model,
        provider=provider,
        tokens_used=tokens_used,
    )


def _extract_json_block(text: str) -> str:
    # 1. Try markdown JSON code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # 2. Try raw JSON object (first { ... } span)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


def _fallback_result(
    raw: str,
    model: str,
    provider: str,
    tokens_used: int,
) -> ReviewResult:
    summary = raw.strip()[:500] if raw.strip() else "Kein lesbares Review erhalten."
    return ReviewResult(
        summary=summary,
        risk_overall="medium",
        uncertainty={"level": 1.0, "sources": ["parse_failure"], "productive": False},
        suggestions=[],
        raw_response=raw,
        model=model,
        provider=provider,
        tokens_used=tokens_used,
    )
