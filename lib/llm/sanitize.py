"""Secrets and sensitive-data redaction before sending diffs to LLMs."""
from __future__ import annotations

import re

# Patterns are ordered from most specific to least specific.
# We intentionally avoid over-aggressive base64 matching to keep code diffs readable.
_PATTERNS: list[re.Pattern[str]] = [
    # PEM private keys (multi-line)
    re.compile(
        r"-----BEGIN [\w ]+ PRIVATE KEY-----.*?-----END [\w ]+ PRIVATE KEY-----",
        re.DOTALL,
    ),
    # JWT tokens (header.payload.signature, base64url-encoded)
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # Common key=value / key: value secret patterns (env-file style)
    re.compile(
        r"(?i)(\b(?:api[_-]?key|token|secret|password|passwd|auth(?:orization)?|"
        r"credential|private[_-]?key|access[_-]?key|client[_-]?secret)\b"
        r"\s*[=:]\s*)"
        r"([^\s'\"\r\n]{6,})",
        re.MULTILINE,
    ),
    # Quoted secrets: key = "value" or key = 'value'
    re.compile(
        r"(?i)(\b(?:api[_-]?key|token|secret|password|passwd|auth(?:orization)?|"
        r"credential|private[_-]?key|access[_-]?key|client[_-]?secret)\b"
        r"\s*[=:]\s*['\"])"
        r"([^'\"]{6,})"
        r"(['\"])",
        re.MULTILINE,
    ),
]


def redact(text: str, extra_patterns: list[str] | None = None) -> str:
    """Return *text* with secrets replaced by ``[REDACTED]``.

    Applies a series of regex-based redaction patterns to the full text.
    """
    for pat in _PATTERNS:
        try:
            text = pat.sub(_replacer, text)
        except Exception:  # noqa: BLE001
            pass

    # Optional policy-provided regex denylist patterns.
    for pattern in extra_patterns or []:
        try:
            compiled = re.compile(pattern, re.MULTILINE)
            text = compiled.sub("[REDACTED]", text)
        except re.error:
            continue
        except Exception:  # noqa: BLE001
            continue
    return text


def _replacer(m: re.Match[str]) -> str:
    groups = m.groups()
    # Pattern has leading group (key portion) + value group
    if len(groups) == 2:
        return groups[0] + "[REDACTED]"
    # Pattern has leading group + value group + trailing quote
    if len(groups) == 3:
        return groups[0] + "[REDACTED]" + groups[2]
    return "[REDACTED]"
