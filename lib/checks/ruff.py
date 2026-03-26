from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from lib.findings import Finding, Severity

from .base import build_uncertainty, iter_matching_files, policy_check_enabled


def run_ruff(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> list[Finding]:
  """Run ruff on Python files and parse JSON output."""
  if not policy_check_enabled("ruff", checks_cfg):
    return []
  if not shutil.which("ruff"):
    log("ruff nicht gefunden - ueberspringe")
    return []

  candidates = iter_matching_files(repo_dir, files, {".py"}, excludes)
  if not candidates:
    return []

  cmd = ["ruff", "check", "--output-format", "json", *[str(path) for path in candidates]]
  result = run_cmd(cmd, repo_dir, check=False)

  output = (result.stdout or result.stderr or "").strip()
  if not output:
    return []

  try:
    entries = json.loads(output)
  except json.JSONDecodeError:
    log("ruff: unparseable output")
    return []

  findings: list[Finding] = []
  for entry in entries:
    code = str(entry.get("code") or "")
    message = str(entry.get("message") or "").strip() or "Ruff finding"
    filename = str(entry.get("filename") or "")
    location = entry.get("location") or {}
    line_raw = location.get("row")

    try:
      line_num = int(line_raw) if line_raw is not None else None
    except (ValueError, TypeError):
      line_num = None

    severity: Severity = "warning"
    if code.startswith("F") or code.startswith("E"):
      severity = "error"

    category = "security" if code.startswith("S") else "correctness"
    fix_available = bool(entry.get("fix"))

    if filename:
      try:
        fp = Path(filename)
        if fp.is_absolute():
          file_rel = str(fp.relative_to(repo_dir))
        else:
          file_rel = filename
      except (ValueError, OSError):
        file_rel = filename
    else:
      file_rel = "unknown.py"

    findings.append(
      Finding(
        severity=severity,
        category=category,
        file=file_rel,
        line=line_num,
        message=message,
        uncertainty=build_uncertainty("ruff", line_num, code or None),
        tool="ruff",
        rule_id=code or None,
        fix_available=fix_available,
      )
    )

  return findings


def run_ruff_autofix(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> int:
  """Run optional Ruff auto-fix and return changed file count."""
  if not policy_check_enabled("ruff", checks_cfg):
    return 0

  ruff_cfg = checks_cfg.get("ruff", {}) if checks_cfg else {}
  if not isinstance(ruff_cfg, dict) or not bool(ruff_cfg.get("autofix", False)):
    return 0

  if not shutil.which("ruff"):
    log("ruff nicht gefunden - autofix uebersprungen")
    return 0

  candidates = iter_matching_files(repo_dir, files, {".py"}, excludes)
  if not candidates:
    return 0

  before: dict[Path, bytes] = {}
  for path in candidates:
    try:
      before[path] = path.read_bytes()
    except OSError:
      continue

  run_cmd(["ruff", "check", "--fix", *[str(path) for path in candidates]], repo_dir, check=False)
  run_cmd(["ruff", "format", *[str(path) for path in candidates]], repo_dir, check=False)

  changed = 0
  for path, old in before.items():
    try:
      new = path.read_bytes()
    except OSError:
      continue
    if old != new:
      changed += 1

  return changed
