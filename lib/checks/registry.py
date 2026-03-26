from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from lib.findings import Finding

from .bandit import run_bandit
from .eslint import run_eslint, run_eslint_autofix
from .ruff import run_ruff, run_ruff_autofix
from .shellcheck import run_shellcheck
from .shfmt import run_shfmt
from .trivy import run_trivy
from .yamllint import run_yamllint


def run_checks(
  repo_dir: Path,
  files: Iterable[Path] | None,
  checks_cfg: dict | None,
  excludes: Iterable[str],
  run_cmd,
  log,
) -> list[Finding]:
  """Run all enabled static checks via central registry."""
  findings: list[Finding] = []
  findings.extend(run_shellcheck(repo_dir, files, excludes, checks_cfg, run_cmd, log))
  findings.extend(run_yamllint(repo_dir, files, excludes, checks_cfg, run_cmd, log))
  findings.extend(run_ruff(repo_dir, files, excludes, checks_cfg, run_cmd, log))
  findings.extend(run_bandit(repo_dir, files, excludes, checks_cfg, run_cmd, log))
  findings.extend(run_eslint(repo_dir, files, excludes, checks_cfg, run_cmd, log))
  findings.extend(run_trivy(repo_dir, files, excludes, checks_cfg, run_cmd, log))
  return findings


def run_autofixes(
  repo_dir: Path,
  files: Iterable[Path] | None,
  checks_cfg: dict | None,
  excludes: Iterable[str],
  run_cmd,
  log,
) -> dict[str, int]:
  """Run all enabled autofixers and return changed-file counters."""
  return {
    "ruff": run_ruff_autofix(repo_dir, files, excludes, checks_cfg, run_cmd, log),
    "eslint": run_eslint_autofix(repo_dir, files, excludes, checks_cfg, run_cmd, log),
    "shfmt": run_shfmt(repo_dir, files, excludes, checks_cfg, run_cmd, log),
  }
