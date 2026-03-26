"""Hash-based redundancy (copy-paste) detection.

Detects files that share identical code blocks using a sliding-window
SHA-256 approach. Findings are emitted as ``severity="question"`` because
the detected duplication might be intentional.

Default: **disabled** (must be opted in via ``checks.redundancy.enabled: true``).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from lib.findings import Finding

_SUPPORTED_SUFFIXES = {".py", ".js", ".ts", ".sh"}
_DEFAULT_BLOCK_SIZE = 6    # lines per sliding window
_DEFAULT_THRESHOLD = 2     # minimum occurrences to flag
_MIN_MEANINGFUL_RATIO = 0.5  # fraction of non-empty/non-comment lines required


def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith(("#", "//", "/*", "*", "*/", "--"))


def _hash_block(lines: list[str]) -> str:
    normalized = "\n".join(line.strip() for line in lines)
    return hashlib.sha256(normalized.encode()).hexdigest()


def run_redundancy_check(
    repo_dir: Path,
    files: list[Path] | None,
    checks_cfg: dict | None,
    log,
) -> list[Finding]:
    """Return findings for duplicated code blocks.

    Args:
        repo_dir: Repository root directory.
        files: Changed-files list, or ``None`` for all-files mode.
        checks_cfg: Policy ``checks`` dict.
        log: Logging callback.

    Returns:
        List of ``Finding`` objects with ``category="maintainability"``.
    """
    cfg = (checks_cfg or {}).get("redundancy", {})
    if isinstance(cfg, bool):
        if not cfg:
            return []
        cfg = {}
    elif not cfg.get("enabled", False):  # default is disabled
        return []

    block_size = int(cfg.get("block_size", _DEFAULT_BLOCK_SIZE))
    threshold = int(cfg.get("threshold", _DEFAULT_THRESHOLD))

    if files is not None:
        candidates = [f for f in files if f.suffix in _SUPPORTED_SUFFIXES]
    else:
        candidates = []
        for suffix in _SUPPORTED_SUFFIXES:
            candidates.extend(repo_dir.rglob(f"*{suffix}"))

    # hash → [(rel_path, start_line)]
    block_locations: dict[str, list[tuple[str, int]]] = {}

    for filepath in candidates:
        try:
            text = filepath.read_text(encoding="utf-8", errors="ignore")
            lines = text.splitlines()
        except OSError:
            continue

        rel = str(filepath.relative_to(repo_dir)) if filepath.is_absolute() else str(filepath)

        for i in range(max(0, len(lines) - block_size + 1)):
            block = lines[i : i + block_size]
            meaningful = [ln for ln in block if not _is_comment_or_blank(ln)]
            if len(meaningful) < max(1, int(block_size * _MIN_MEANINGFUL_RATIO)):
                continue
            h = _hash_block(block)
            block_locations.setdefault(h, []).append((rel, i + 1))

    findings: list[Finding] = []
    seen: set[str] = set()

    for h, locations in block_locations.items():
        if len(locations) < threshold or h in seen:
            continue
        seen.add(h)
        first_file, first_line = locations[0]
        preview = ", ".join(f"{f}:{ln}" for f, ln in locations[:4])
        if len(locations) > 4:
            preview += f", … ({len(locations) - 4} weitere)"
        findings.append(
            Finding(
                severity="question",
                category="maintainability",
                file=first_file,
                line=first_line,
                message=f"Duplizierter Code-Block ({len(locations)}×): {preview}",
                tool="redundancy",
                rule_id="duplicate_block",
            )
        )

    if findings:
        log(f"Redundanz-Analyse: {len(findings)} duplizierter Block/Blöcke gefunden")

    return findings
