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
  *,
  only_tools: set[str] | None = None,
  target_files_by_tool: dict[str, list[Path]] | None = None,
) -> dict[str, int]:
  """Run enabled autofixers and return changed-file counters.

  When ``only_tools`` is provided, targeted autofixers only run for the named
  tools. ``target_files_by_tool`` may further narrow each autofixer to the files
  that produced ``fix_available`` findings and may contain relative or absolute
  paths; relative paths are normalized against ``repo_dir`` before dispatch.

  ``shfmt`` intentionally remains a separate policy-driven formatting pass
  because it does not emit structured ``fix_available`` findings in the same way
  Ruff/ESLint do.
  """
  selected_tools = {tool.strip().lower() for tool in only_tools} if only_tools is not None else None
  targets = target_files_by_tool or {}
  default_files = list(files) if files is not None else None

  def normalize_tool_targets(tool_files: list[Path] | None) -> list[Path] | None:
    if tool_files is None:
      return None
    normalized: list[Path] = []
    for path in tool_files:
      normalized.append(path if path.is_absolute() else (repo_dir / path))
    return normalized

  def resolve_files(tool_name: str) -> list[Path] | None:
    if selected_tools is not None and tool_name not in selected_tools:
      return []
    explicit_targets = targets.get(tool_name)
    if explicit_targets is not None:
      return normalize_tool_targets(explicit_targets)
    return default_files

  ruff_files = resolve_files("ruff")
  eslint_files = resolve_files("eslint")

  return {
    "ruff": run_ruff_autofix(repo_dir, ruff_files, excludes, checks_cfg, run_cmd, log) if ruff_files != [] else 0,
    "eslint": run_eslint_autofix(repo_dir, eslint_files, excludes, checks_cfg, run_cmd, log) if eslint_files != [] else 0,
    "shfmt": run_shfmt(repo_dir, files, excludes, checks_cfg, run_cmd, log),
  }
