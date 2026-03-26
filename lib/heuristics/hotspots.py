"""Hotspot detection based on git churn."""
from __future__ import annotations

from pathlib import Path

from lib.checks.base import build_uncertainty
from lib.findings import Finding

DEFAULT_THRESHOLD = 10


def run_hotspot_check(
  repo_dir: Path,
  files: list[Path] | None,
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> list[Finding]:
  """Return findings for files changed frequently in the last 90 days."""
  cfg = (checks_cfg or {}).get("hotspots", {})
  if isinstance(cfg, bool):
    if not cfg:
      return []
    cfg = {}
  elif isinstance(cfg, dict) and not cfg.get("enabled", False):
    return []

  threshold = int((cfg or {}).get("churn_threshold", DEFAULT_THRESHOLD))
  result = run_cmd(
    ["git", "log", "--pretty=format:", "--name-only", "--since=90.days.ago"],
    repo_dir,
    check=False,
  )
  if result.returncode != 0 or not (result.stdout or "").strip():
    return []

  changed_only: set[str] | None = None
  if files is not None:
    changed_only = set()
    for candidate in files:
      try:
        changed_only.add(str(candidate.relative_to(repo_dir)))
      except ValueError:
        changed_only.add(str(candidate))

  churn: dict[str, int] = {}
  for raw in result.stdout.splitlines():
    rel = raw.strip()
    if not rel:
      continue
    if changed_only is not None and rel not in changed_only:
      continue
    churn[rel] = churn.get(rel, 0) + 1

  findings: list[Finding] = []
  for rel, count in sorted(churn.items(), key=lambda item: (-item[1], item[0])):
    if count < threshold:
      continue
    severity = "error" if count >= 30 else "warning" if count >= 15 else "info"
    findings.append(
      Finding(
        severity=severity,
        category="maintainability",
        file=rel,
        line=None,
        message=f"Hotspot: {count} Anderungen in den letzten 90 Tagen",
        tool="hotspots",
        rule_id="churn",
        uncertainty=build_uncertainty("hotspots", None, "churn"),
      )
    )

  if findings:
    log(f"Hotspot-Analyse: {len(findings)} Hotspot(s) gefunden")
  return findings
