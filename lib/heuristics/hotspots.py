"""Git-churn-based hotspot detection.

Files that change frequently carry higher risk – detecting them early lets the
LLM review focus its risk assessment on the most volatile areas.
"""
from __future__ import annotations

from pathlib import Path

from lib.checks.base import build_uncertainty
from lib.findings import Finding

# Default: flag files changed ≥10 times in the last 90 days.
_DEFAULT_THRESHOLD = 10

# (min_count, severity) – checked in order, first match wins.
_SEVERITY_BANDS = [
    (30, "error"),
    (15, "warning"),
    (0, "info"),
]


def run_hotspot_check(
    repo_dir: Path,
    files: list[Path] | None,
    checks_cfg: dict | None,
    run_cmd,
    log,
) -> list[Finding]:
    """Return findings for files with high git-churn in the last 90 days.

    Args:
        repo_dir: Repository root directory.
        files: Changed-files list, or ``None`` for all-files mode.
        checks_cfg: Policy ``checks`` dict.
        run_cmd: Command runner from the worker.
        log: Logging callback.

    Returns:
        List of ``Finding`` objects with ``category="maintainability"``.
    """
    cfg = (checks_cfg or {}).get("hotspots", {})
    if isinstance(cfg, bool):
        if not cfg:
            return []
        cfg = {}
    elif not cfg.get("enabled", True):
        return []

    threshold = int(cfg.get("churn_threshold", _DEFAULT_THRESHOLD))

    result = run_cmd(
        ["git", "log", "--pretty=format:", "--name-only", "--since=90.days.ago"],
        repo_dir,
        check=False,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return []

    churn: dict[str, int] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            churn[line] = churn.get(line, 0) + 1

    if files is not None:
        rel_files: set[str] = set()
        for f in files:
            try:
                rel_files.add(str(f.relative_to(repo_dir)))
            except ValueError:
                rel_files.add(str(f))
        churn = {k: v for k, v in churn.items() if k in rel_files}

    findings: list[Finding] = []
    for file_path, count in sorted(churn.items(), key=lambda x: -x[1]):
        if count < threshold:
            continue
        severity = "info"
        for min_count, sev in _SEVERITY_BANDS:
            if count >= min_count:
                severity = sev
                break
        findings.append(
            Finding(
                severity=severity,  # type: ignore[arg-type]
                category="maintainability",
                file=file_path,
                line=None,
                message=f"Hotspot: {count} Änderungen in 90 Tagen – erhöhtes Fehlerrisiko",
                tool="hotspots",
                rule_id="churn",
                uncertainty=build_uncertainty("hotspots", None, "churn"),
            )
        )

    if findings:
        log(f"Hotspot-Analyse: {len(findings)} Hotspot(s) gefunden")

    return findings
