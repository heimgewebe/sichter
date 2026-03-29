"""Version-drift detection across dependency and toolchain files.

Drift is not an error – it's an observation that pinned versions in one file
diverge from declarations in another. Findings carry category="drift" and do
*not* trigger auto-fixes.

Supported source pairs:
    - ``pyproject.toml`` ↔ ``requirements.txt``
    - ``toolchain.versions.yml`` ↔ ``Dockerfile`` (ARG/ENV pinning)
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
        # Strip extras (e.g. requests[security]) before matching version spec
        line = re.sub(r"\[.*?\]", "", line)
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

    # toolchain.versions.yml vs Dockerfile (if both exist)
    toolchain_file = repo_dir / "toolchain.versions.yml"
    dockerfile = repo_dir / "Dockerfile"
    if toolchain_file.exists() and dockerfile.exists():
        try:
            tc_versions = _parse_toolchain_yml(toolchain_file.read_text(encoding="utf-8"))
            df_versions = _parse_dockerfile_args(dockerfile.read_text(encoding="utf-8"))
            for tool, tc_ver in tc_versions.items():
                df_ver = df_versions.get(tool)
                if df_ver is not None and tc_ver != df_ver:
                    findings.append(
                        Finding(
                            severity="warning",
                            category="drift",
                            file="Dockerfile",
                            line=None,
                            message=(
                                f"Toolchain-Drift: {tool} – Dockerfile: "
                                f"'{df_ver}', toolchain.versions.yml: '{tc_ver}'"
                            ),
                            tool="drift",
                            rule_id="toolchain_mismatch",
                        )
                    )
        except (OSError, UnicodeDecodeError) as exc:
            log(f"Toolchain-Drift-Check fehlgeschlagen: {exc}")

    if findings:
        log(f"Drift-Analyse: {len(findings)} Versionsabweichung(en) gefunden")

    return findings


def _parse_toolchain_yml(text: str) -> dict[str, str]:
    """Parse ``toolchain.versions.yml`` into {tool -> version}.

    Uses ``yaml.safe_load`` for correctness with comments, quoted values, and
    other YAML features.  Only top-level scalar string/number values are
    considered; nested structures are silently skipped.
    """
    import yaml as _yaml  # pyyaml is already a project dependency

    try:
        data = _yaml.safe_load(text)
    except _yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}

    versions: dict[str, str] = {}
    for key, val in data.items():
        if not isinstance(val, (str, int, float)):
            continue  # skip nested structures, lists, etc.
        tool = str(key).lower().strip()
        ver = str(val).strip().lstrip("v")
        if tool and ver:
            versions[tool] = ver
    return versions


def _parse_dockerfile_args(text: str) -> dict[str, str]:
    """Extract ARG/ENV version pins from Dockerfile-like content."""
    versions: dict[str, str] = {}
    pattern = re.compile(
        r"^(?:ARG|ENV)\s+([A-Za-z0-9_]+(?:_VER(?:SION)?|VERSION|VER))[\s=](.+)$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        raw_name = m.group(1)
        raw_ver = m.group(2).strip().strip('"\'').lstrip("v")
        tool = re.sub(r"[_-](?:VER(?:SION)?|VERSION|VER)$", "", raw_name, flags=re.IGNORECASE)
        versions[tool.lower()] = raw_ver
    return versions
