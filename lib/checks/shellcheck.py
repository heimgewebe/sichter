from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from lib.findings import Finding

from .base import build_uncertainty, normalize_severity, policy_check_enabled, iter_matching_files


def run_shellcheck(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> list[Finding]:
  """Run shellcheck and parse gcc-style output."""
  if not policy_check_enabled("shellcheck", checks_cfg):
    return []
  if not shutil.which("shellcheck"):
    log("shellcheck nicht gefunden - ueberspringe")
    return []

  findings: list[Finding] = []
  candidates = iter_matching_files(repo_dir, files, {".sh"}, excludes)

  for script in candidates:
    result = run_cmd(["shellcheck", "-f", "gcc", "-x", str(script)], repo_dir, check=False)
    if result.returncode == 0:
      continue

    output = result.stdout or result.stderr
    for raw in (output or "").splitlines():
      line = raw.strip()
      if not line:
        continue

      parts = line.split(":", 3)
      if len(parts) < 4:
        log(f"shellcheck: {script}: unparseable line: {line}")
        continue

      file_path = parts[0]
      line_num = parts[1]
      rest = parts[3].strip()

      if ": " in rest:
        sev_part, msg_part = rest.split(": ", 1)
        sev = sev_part.lower()
        message = msg_part
      else:
        sev = "warning"
        message = rest

      rule_id = None
      if "[SC" in message and "]" in message:
        rule_start = message.rfind("[SC")
        rule_end = message.find("]", rule_start)
        if rule_end > rule_start:
          rule_id = message[rule_start + 1 : rule_end]
          message = message[:rule_start].rstrip()

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
          uncertainty=build_uncertainty("shellcheck", line_int, rule_id),
          tool="shellcheck",
          rule_id=rule_id,
        )
      )

  return findings
