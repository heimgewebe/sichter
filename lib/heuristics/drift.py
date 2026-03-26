"""Simple version drift detection between dependency manifests."""
from __future__ import annotations

import re
from pathlib import Path

from lib.findings import Finding


def _normalize_package(name: str) -> str:
  return name.strip().lower().replace("-", "_").replace(".", "_")


def _parse_requirements(text: str) -> dict[str, str]:
  versions: dict[str, str] = {}
  for raw in text.splitlines():
    line = raw.strip()
    if not line or line.startswith(("#", "-")):
      continue
    line = line.split(";", 1)[0].strip()
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*([><=!~^,\s\d.*]+)?$", line)
    if not match:
      continue
    versions[_normalize_package(match.group(1))] = (match.group(2) or "").strip()
  return versions


def _extract_dep(line: str) -> tuple[str, str] | None:
  stripped = line.strip().strip(",").strip("\"").strip("'")
  if not stripped:
    return None
  match = re.match(r"^([A-Za-z0-9_.-]+)\s*([><=!~^,\s\d.*]+)?$", stripped)
  if not match:
    return None
  return _normalize_package(match.group(1)), (match.group(2) or "").strip()


def _parse_pyproject_deps(text: str) -> dict[str, str]:
  versions: dict[str, str] = {}
  in_dependencies = False
  for raw in text.splitlines():
    stripped = raw.strip()
    if stripped.startswith("dependencies") and "[" in stripped:
      in_dependencies = True
      inline = stripped.split("[", 1)[1].rsplit("]", 1)[0].strip()
      if inline:
        for item in inline.split(","):
          parsed = _extract_dep(item)
          if parsed:
            versions[parsed[0]] = parsed[1]
        in_dependencies = False
      continue
    if not in_dependencies:
      continue
    if stripped == "]":
      in_dependencies = False
      continue
    parsed = _extract_dep(stripped)
    if parsed:
      versions[parsed[0]] = parsed[1]
  return versions


def run_drift_check(repo_dir: Path, checks_cfg: dict | None, log) -> list[Finding]:
  """Return drift findings for mismatched dependency specs."""
  cfg = (checks_cfg or {}).get("drift", {})
  if isinstance(cfg, bool):
    if not cfg:
      return []
  elif isinstance(cfg, dict) and not cfg.get("enabled", False):
    return []

  pyproject = repo_dir / "pyproject.toml"
  requirements = repo_dir / "requirements.txt"
  if not pyproject.exists() or not requirements.exists():
    return []

  try:
    pyproject_deps = _parse_pyproject_deps(pyproject.read_text(encoding="utf-8"))
    requirements_deps = _parse_requirements(requirements.read_text(encoding="utf-8"))
  except OSError as exc:
    log(f"Drift-Check fehlgeschlagen: {exc}")
    return []

  findings: list[Finding] = []
  for package, requirements_spec in sorted(requirements_deps.items()):
    pyproject_spec = pyproject_deps.get(package)
    if pyproject_spec is None or not pyproject_spec or not requirements_spec:
      continue
    if pyproject_spec == requirements_spec:
      continue
    findings.append(
      Finding(
        severity="warning",
        category="drift",
        file="requirements.txt",
        line=None,
        message=(
          f"Versionsdrift fur {package}: requirements.txt={requirements_spec!r}, "
          f"pyproject.toml={pyproject_spec!r}"
        ),
        tool="drift",
        rule_id="version_mismatch",
      )
    )

  if findings:
    log(f"Drift-Analyse: {len(findings)} Versionsabweichung(en) gefunden")
  return findings
