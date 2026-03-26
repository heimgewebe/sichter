"""Version-drift detection between pyproject.toml and requirements.txt.

Drift is not an error – it's an observation that pinned dependencies in
``requirements.txt`` diverge from the declared ranges in ``pyproject.toml``.
These findings are category="drift" and do *not* trigger auto-fixes.
"""
from __future__ import annotations

import re
from pathlib import Path

from lib.findings import Finding


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_requirements(text: str) -> dict[str, str]:
    """Parse requirements.txt lines into {pkg_key → version_spec}."""
    versions: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        # Strip extras, env markers
        line = re.split(r"[;# ]", line)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*([><=!~^,\s\d.*]+)?", line)
        if match:
            pkg = _normalize_pkg(match.group(1))
            spec = (match.group(2) or "").strip()
            versions[pkg] = spec
    return versions


def _parse_pyproject_deps(text: str) -> dict[str, str]:
    """Naively parse ``[project] dependencies`` from pyproject.toml text.

    Uses line-by-line parsing to avoid requiring the ``tomllib`` import (which
    is 3.11+) or any third-party TOML library.
    """
    versions: dict[str, str] = {}
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped != "[project]":
            in_deps = False
        if re.match(r"^dependencies\s*=\s*\[", stripped):
            in_deps = True
            # Inline single-line list? Extract.
            inner = re.search(r"\[(.+)\]", stripped)
            if inner:
                for item in inner.group(1).split(","):
                    _extract_dep(item.strip().strip('"\''), versions)
                in_deps = False
            continue
        if in_deps:
            if stripped == "]":
                in_deps = False
                continue
            _extract_dep(stripped.strip('",').strip("'"), versions)
    return versions


def _extract_dep(dep_str: str, target: dict[str, str]) -> None:
    dep_str = dep_str.strip()
    if not dep_str or dep_str.startswith("#"):
        return
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*([><=!~^,\s\d.*]+)?", dep_str)
    if match:
        pkg = _normalize_pkg(match.group(1))
        spec = (match.group(2) or "").strip()
        target[pkg] = spec


def _normalize_pkg(name: str) -> str:
    """Normalize package name for comparison (lowercase, underscore-separated)."""
    return name.lower().replace("-", "_").replace(".", "_")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_drift_check(
    repo_dir: Path,
    checks_cfg: dict | None,
    log,
) -> list[Finding]:
    """Return findings for version mismatches between dependency files.

    Args:
        repo_dir: Repository root directory.
        checks_cfg: Policy ``checks`` dict.
        log: Logging callback.

    Returns:
        List of ``Finding`` objects with ``category="drift"``.
    """
    cfg = (checks_cfg or {}).get("drift", {})
    if isinstance(cfg, bool):
        if not cfg:
            return []
        cfg = {}
    elif not cfg.get("enabled", True):
        return []

    findings: list[Finding] = []

    pyproject = repo_dir / "pyproject.toml"
    requirements = repo_dir / "requirements.txt"

    if pyproject.exists() and requirements.exists():
        try:
            pyproj_text = pyproject.read_text(encoding="utf-8")
            req_text = requirements.read_text(encoding="utf-8")
            pyproj_versions = _parse_pyproject_deps(pyproj_text)
            req_versions = _parse_requirements(req_text)

            for pkg, req_spec in req_versions.items():
                pyproj_spec = pyproj_versions.get(pkg)
                if pyproj_spec is None:
                    continue  # indirect dependency – skip
                if req_spec and pyproj_spec and req_spec != pyproj_spec:
                    findings.append(
                        Finding(
                            severity="warning",
                            category="drift",
                            file="requirements.txt",
                            line=None,
                            message=(
                                f"Versionsdrift: {pkg} – requirements.txt: "
                                f"'{req_spec}', pyproject.toml: '{pyproj_spec}'"
                            ),
                            tool="drift",
                            rule_id="version_mismatch",
                        )
                    )
        except (OSError, UnicodeDecodeError) as exc:
            log(f"Drift-Check fehlgeschlagen: {exc}")

    if findings:
        log(f"Drift-Analyse: {len(findings)} Versionsabweichung(en) gefunden")

    return findings
