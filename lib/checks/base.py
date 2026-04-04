from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from fnmatch import translate
from functools import lru_cache
from pathlib import Path
from typing import Protocol, cast

from lib.findings import Finding, Severity

RunCmd = Callable[..., object]
Logger = Callable[[str], None]


class Check(Protocol):
  name: str

  def detect(self, repo_dir: Path, checks_cfg: dict | None) -> bool:
    """Return whether this check should run in current environment."""

  def run(
    self,
    repo_dir: Path,
    files: Iterable[Path] | None,
    excludes: Iterable[str],
    checks_cfg: dict | None,
    run_cmd: RunCmd,
    log: Logger,
  ) -> list[Finding]:
    """Return findings for this check."""

  def autofix(
    self,
    repo_dir: Path,
    files: Iterable[Path] | None,
    excludes: Iterable[str],
    checks_cfg: dict | None,
    run_cmd: RunCmd,
    log: Logger,
  ) -> int:
    """Apply optional auto-fixes and return changed file count."""


def policy_check_enabled(name: str, checks_cfg: dict | None) -> bool:
  """Return whether a check is enabled in policy."""
  if not checks_cfg:
    return False

  value = checks_cfg.get(name, False)
  if isinstance(value, bool):
    return value
  if isinstance(value, dict):
    return bool(value.get("enabled", False) or value.get("autofix", False))
  return False


def normalize_severity(severity: str) -> Severity:
  """Normalize arbitrary strings to known Finding severities."""
  severity_lower = severity.lower()
  if severity_lower in {"info", "warning", "error", "critical", "question"}:
    return cast(Severity, severity_lower)
  return "warning"



@lru_cache(maxsize=16)
def compile_excludes(excludes: tuple[str, ...]) -> re.Pattern | None:
  """Compile glob patterns into a single regular expression.

  Args:
    excludes: Tuple of glob patterns

  Returns:
    Compiled regular expression or None if excludes is empty
  """
  if not excludes:
    return None
  # fnmatch.translate produces a regex string. We wrap each in a non-capturing group.
  regex_str = "|".join(f"(?:{translate(ex)})" for ex in excludes)
  return re.compile(regex_str)


def is_excluded(path_str: str, excludes: Iterable[str] | re.Pattern | None) -> bool:
  """Check if path matches any exclusion pattern using compiled regex.

  Args:
    path_str: Path string to check
    excludes: Iterable of exclusion glob patterns or a pre-compiled regex

  Returns:
    True if path matches any exclusion pattern, False otherwise
  """
  if isinstance(excludes, re.Pattern):
    return bool(excludes.match(path_str))
  if excludes is None:
    return False

  excludes_tuple = tuple(excludes)
  compiled_re = compile_excludes(excludes_tuple)
  if compiled_re is None:
    return False
  return bool(compiled_re.match(path_str))


def build_uncertainty(tool: str, line: int | None, rule_id: str | None) -> dict:
  """Build a lightweight uncertainty payload for static findings."""
  level = 0.15
  sources: list[str] = []

  if line is None:
    level += 0.15
    sources.append("missing_line")
  if not rule_id:
    level += 0.10
    sources.append("missing_rule_id")

  if level > 1.0:
    level = 1.0

  return {
    "level": level,
    "sources": sources,
    "productive": True,
    "tool": tool,
  }


def iter_matching_files(
  repo_dir: Path,
  files: Iterable[Path] | None,
  suffixes: set[str],
  excludes: Iterable[str],
) -> list[Path]:
  """Return files matching suffixes and excludes, in all-files or changed-files mode."""
  if files is None:
    candidates: list[Path] = []
    for suffix in suffixes:
      candidates.extend(repo_dir.rglob(f"*{suffix}"))
  else:
    candidates = list(files)

  selected: list[Path] = []
  compiled_re = compile_excludes(tuple(excludes))
  for candidate in candidates:
    if candidate.suffix not in suffixes:
      continue
    try:
      rel = candidate.relative_to(repo_dir)
    except ValueError:
      continue
    if is_excluded(str(rel), compiled_re):
      continue
    selected.append(candidate)

  return selected
