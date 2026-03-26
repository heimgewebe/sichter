"""Hash-based duplicate block detection."""
from __future__ import annotations

import hashlib
from pathlib import Path

from lib.findings import Finding

SUPPORTED_SUFFIXES = {".py", ".js", ".ts", ".sh"}


def _is_noise(line: str) -> bool:
  stripped = line.strip()
  return not stripped or stripped.startswith(("#", "//", "/*", "*", "*/", "--"))


def _hash_block(lines: list[str]) -> str:
  normalized = "\n".join(line.strip() for line in lines)
  return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_redundancy_check(
  repo_dir: Path,
  files: list[Path] | None,
  checks_cfg: dict | None,
  log,
) -> list[Finding]:
  """Return findings for duplicated code blocks."""
  cfg = (checks_cfg or {}).get("redundancy", {})
  if isinstance(cfg, bool):
    if not cfg:
      return []
    cfg = {}
  elif isinstance(cfg, dict) and not cfg.get("enabled", False):
    return []

  block_size = int((cfg or {}).get("block_size", 6))
  threshold = int((cfg or {}).get("threshold", 2))
  candidates: list[Path]
  if files is None:
    candidates = []
    for suffix in SUPPORTED_SUFFIXES:
      candidates.extend(repo_dir.rglob(f"*{suffix}"))
  else:
    candidates = [path for path in files if path.suffix in SUPPORTED_SUFFIXES]

  occurrences: dict[str, list[tuple[str, int]]] = {}
  for candidate in candidates:
    try:
      rel = str(candidate.relative_to(repo_dir))
      lines = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
    except (OSError, ValueError):
      continue
    for index in range(max(0, len(lines) - block_size + 1)):
      block = lines[index:index + block_size]
      meaningful = [line for line in block if not _is_noise(line)]
      if len(meaningful) < max(1, block_size // 2):
        continue
      occurrences.setdefault(_hash_block(block), []).append((rel, index + 1))

  findings: list[Finding] = []
  for locations in occurrences.values():
    if len(locations) < threshold:
      continue
    first_file, first_line = locations[0]
    preview = ", ".join(f"{path}:{line}" for path, line in locations[:4])
    findings.append(
      Finding(
        severity="question",
        category="maintainability",
        file=first_file,
        line=first_line,
        message=f"Duplizierter Code-Block ({len(locations)}x): {preview}",
        tool="redundancy",
        rule_id="duplicate_block",
      )
    )

  if findings:
    log(f"Redundanz-Analyse: {len(findings)} duplizierte Blocke gefunden")
  return findings
