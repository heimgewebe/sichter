from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from .base import iter_matching_files, policy_check_enabled


def run_shfmt(
  repo_dir: Path,
  files: Iterable[Path] | None,
  excludes: Iterable[str],
  checks_cfg: dict | None,
  run_cmd,
  log,
) -> int:
  """Run shfmt as optional auto-fix pass and return changed file count."""
  if not policy_check_enabled("shfmt_fix", checks_cfg):
    return 0
  if not shutil.which("shfmt"):
    log("shfmt nicht gefunden - ueberspringe")
    return 0

  candidates = iter_matching_files(repo_dir, files, {".sh"}, excludes)
  changed = 0
  for script in candidates:
    try:
      before = script.read_bytes()
    except OSError:
      continue

    result = run_cmd(["shfmt", "-w", str(script)], repo_dir, check=False)
    if result.returncode != 0:
      log(f"shfmt failed for {script}: {result.stderr.strip()}")
      continue

    try:
      after = script.read_bytes()
    except OSError:
      continue

    if before != after:
      changed += 1

  return changed
