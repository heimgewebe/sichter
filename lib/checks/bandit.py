from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from lib.findings import Finding

from .base import build_uncertainty, iter_matching_files, policy_check_enabled

from fnmatch import fnmatch


def run_bandit(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> list[Finding]:
  """Run Bandit security scan and parse JSON output."""
  if not policy_check_enabled("bandit", checks_cfg):
    return []
  if not shutil.which("bandit"):
    log("bandit nicht gefunden - ueberspringe")
    return []

  excludes_list = list(excludes)

  if files is None:
    cmd = ["bandit", "-f", "json", "-r", "."]
  else:
    candidates = iter_matching_files(repo_dir, files, {".py"}, excludes_list)
    if not candidates:
      return []
    cmd = ["bandit", "-f", "json", *[str(path) for path in candidates]]

  result = run_cmd(cmd, repo_dir, check=False)
  output = (result.stdout or result.stderr or "").strip()
  if not output:
    return []

  try:
    data = json.loads(output)
  except json.JSONDecodeError:
    log("bandit: unparseable output")
    return []

  severity_map = {
    "LOW": "warning",
    "MEDIUM": "error",
    "HIGH": "critical",
  }

  findings: list[Finding] = []
  for item in data.get("results", []):
    severity = severity_map.get(str(item.get("issue_severity", "")).upper(), "warning")
    filename = str(item.get("filename") or "unknown.py")
    line_raw = item.get("line_number")
    rule_id = str(item.get("test_id") or "") or None
    message = str(item.get("issue_text") or "Bandit finding")

    try:
      line_num = int(line_raw) if line_raw is not None else None
    except (ValueError, TypeError):
      line_num = None

    try:
      fp = Path(filename)
      if fp.is_absolute():
        file_rel = str(fp.relative_to(repo_dir))
      else:
        file_rel = filename
    except (ValueError, OSError):
      file_rel = filename

    # In all-files mode, apply policy excludes to results since bandit -r .
    # does its own file discovery and bypasses iter_matching_files filtering.
    if files is None and excludes_list:
      if any(fnmatch(file_rel, pattern) for pattern in excludes_list):
        continue

    findings.append(
      Finding(
        severity=severity,
        category="security",
        file=file_rel,
        line=line_num,
        message=message,
        evidence=str(item.get("more_info") or "") or None,
        uncertainty=build_uncertainty("bandit", line_num, rule_id),
        tool="bandit",
        rule_id=rule_id,
      )
    )

  return findings
