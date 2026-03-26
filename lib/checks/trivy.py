from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from lib.findings import Finding

from .base import build_uncertainty, policy_check_enabled


def run_trivy(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> list[Finding]:
  """Run Trivy file-system scan and parse JSON vulnerabilities."""
  del files
  del excludes

  if not policy_check_enabled("trivy", checks_cfg):
    return []
  if not shutil.which("trivy"):
    log("trivy nicht gefunden - ueberspringe")
    return []

  result = run_cmd(["trivy", "fs", "--quiet", "--format", "json", "."], repo_dir, check=False)
  output = (result.stdout or result.stderr or "").strip()
  if not output:
    return []

  try:
    data = json.loads(output)
  except json.JSONDecodeError:
    log("trivy: unparseable output")
    return []

  severity_map = {
    "UNKNOWN": "warning",
    "LOW": "warning",
    "MEDIUM": "error",
    "HIGH": "critical",
    "CRITICAL": "critical",
  }

  findings: list[Finding] = []
  for result_item in data.get("Results", []):
    target = str(result_item.get("Target") or "unknown")
    vulnerabilities = result_item.get("Vulnerabilities") or []
    for vuln in vulnerabilities:
      vuln_id = str(vuln.get("VulnerabilityID") or "")
      pkg = str(vuln.get("PkgName") or "")
      title = str(vuln.get("Title") or "Trivy finding")
      sev = severity_map.get(str(vuln.get("Severity") or "").upper(), "warning")
      message = f"{vuln_id}: {title}" if vuln_id else title
      if pkg:
        message = f"{message} ({pkg})"

      findings.append(
        Finding(
          severity=sev,
          category="security",
          file=target,
          line=None,
          message=message,
          evidence=str(vuln.get("PrimaryURL") or "") or None,
          uncertainty=build_uncertainty("trivy", None, vuln_id or None),
          tool="trivy",
          rule_id=vuln_id or None,
        )
      )

  return findings
