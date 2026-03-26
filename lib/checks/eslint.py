from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from lib.findings import Finding

from .base import build_uncertainty, iter_matching_files, policy_check_enabled

_ESLINT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
_ESLINT_CONFIGS = (
  ".eslintrc",
  ".eslintrc.js",
  ".eslintrc.cjs",
  ".eslintrc.json",
  "eslint.config.js",
  "eslint.config.cjs",
  "eslint.config.mjs",
)


def _has_eslint_config(repo_dir: Path) -> bool:
  return any((repo_dir / name).exists() for name in _ESLINT_CONFIGS)


def run_eslint(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> list[Finding]:
  """Run ESLint on JS/TS files and parse JSON output."""
  if not policy_check_enabled("eslint", checks_cfg):
    return []
  if not shutil.which("eslint"):
    log("eslint nicht gefunden - ueberspringe")
    return []
  if not _has_eslint_config(repo_dir):
    return []

  candidates = iter_matching_files(repo_dir, files, _ESLINT_SUFFIXES, excludes)
  if not candidates:
    return []

  cmd = ["eslint", "--format", "json", *[str(path) for path in candidates]]
  result = run_cmd(cmd, repo_dir, check=False)
  output = (result.stdout or result.stderr or "").strip()
  if not output:
    return []

  try:
    entries = json.loads(output)
  except json.JSONDecodeError:
    log("eslint: unparseable output")
    return []

  findings: list[Finding] = []
  for file_entry in entries:
    file_path = str(file_entry.get("filePath") or "unknown.js")
    try:
      fp = Path(file_path)
      if fp.is_absolute():
        file_rel = str(fp.relative_to(repo_dir))
      else:
        file_rel = file_path
    except (ValueError, OSError):
      file_rel = file_path

    for msg in file_entry.get("messages", []):
      line_raw = msg.get("line")
      rule_id = str(msg.get("ruleId") or "") or None
      sev_raw = int(msg.get("severity") or 1)
      severity = "error" if sev_raw >= 2 else "warning"
      message = str(msg.get("message") or "ESLint finding")
      fix_available = bool(msg.get("fix"))

      try:
        line_num = int(line_raw) if line_raw is not None else None
      except (ValueError, TypeError):
        line_num = None

      findings.append(
        Finding(
          severity=severity,
          category="correctness",
          file=file_rel,
          line=line_num,
          message=message,
          uncertainty=build_uncertainty("eslint", line_num, rule_id),
          tool="eslint",
          rule_id=rule_id,
          fix_available=fix_available,
        )
      )

  return findings


def run_eslint_autofix(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> int:
  """Run optional ESLint --fix and return changed file count."""
  if not policy_check_enabled("eslint", checks_cfg):
    return 0

  eslint_cfg = checks_cfg.get("eslint", {}) if checks_cfg else {}
  if not isinstance(eslint_cfg, dict) or not bool(eslint_cfg.get("autofix", False)):
    return 0

  if not shutil.which("eslint"):
    log("eslint nicht gefunden - autofix uebersprungen")
    return 0
  if not _has_eslint_config(repo_dir):
    return 0

  candidates = iter_matching_files(repo_dir, files, _ESLINT_SUFFIXES, excludes)
  if not candidates:
    return 0

  before: dict[Path, bytes] = {}
  for path in candidates:
    try:
      before[path] = path.read_bytes()
    except OSError:
      continue

  run_cmd(["eslint", "--fix", *[str(path) for path in candidates]], repo_dir, check=False)

  changed = 0
  for path, old in before.items():
    try:
      new = path.read_bytes()
    except OSError:
      continue
    if old != new:
      changed += 1

  return changed
