from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from lib.findings import Finding

from .base import build_uncertainty, normalize_severity, policy_check_enabled, iter_matching_files


def run_yamllint(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> list[Finding]:
  """Run yamllint and parse parsable-format output."""
  if not policy_check_enabled("yamllint", checks_cfg):
    return []
  if not shutil.which("yamllint"):
    log("yamllint nicht gefunden - ueberspringe")
    return []

  findings: list[Finding] = []
  candidates = iter_matching_files(repo_dir, files, {".yml", ".yaml"}, excludes)

  for doc in candidates:
    result = run_cmd(["yamllint", "-f", "parsable", str(doc)], repo_dir, check=False)
    if result.returncode == 0:
      continue

    output = result.stdout or result.stderr
    for raw in (output or "").splitlines():
      line = raw.strip()
      if not line:
        continue

      parts = line.split(":", 3)
      if len(parts) < 4:
        log(f"yamllint: {doc}: unparseable line: {line}")
        continue

      file_path = parts[0]
      line_num = parts[1]
      rest = parts[3].strip()

      sev = "warning"
      message = rest
      rule_id = None

      if rest.startswith("["):
        bracket_end = rest.find("]")
        if bracket_end > 0:
          sev = rest[1:bracket_end].lower()
          message = rest[bracket_end + 1 :].strip()

      if "(" in message and ")" in message:
        paren_start = message.rfind("(")
        paren_end = message.find(")", paren_start)
        if paren_end > paren_start:
          rule_id = message[paren_start + 1 : paren_end]
          message = message[:paren_start].strip()

      try:
        line_int = int(line_num)
      except ValueError:
        line_int = None

      try:
        fp = Path(file_path)
        if fp.is_absolute():
          file_rel = str(fp.relative_to(repo_dir))
        else:
          file_rel = file_path
      except (ValueError, OSError):
        file_rel = file_path

      findings.append(
        Finding(
          severity=normalize_severity(sev),
          category="correctness",
          file=file_rel,
          line=line_int,
          message=message,
          uncertainty=build_uncertainty("yamllint", line_int, rule_id),
          tool="yamllint",
          rule_id=rule_id,
        )
      )

  return findings
