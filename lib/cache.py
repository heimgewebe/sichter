"""File-based result cache for sichter checks.

Cache key: ``repo + commit_hash + check_name + policy_hash``
Storage:   ``~/.cache/sichter/<sha256(key)>.json``
TTL:       7 days (configurable)

Cache write failures are silently ignored – correctness must not depend on
the cache being available.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "sichter"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 days


# ---------------------------------------------------------------------------
# Core get/set
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = hashlib.sha256(key.encode()).hexdigest()
    return CACHE_DIR / f"{safe}.json"


def cache_get(key: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict | None:
    """Return cached payload or ``None`` if expired / missing / corrupt."""
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(data.get("_ts", 0)) > ttl_seconds:
            path.unlink(missing_ok=True)
            return None
        return data.get("payload")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def cache_set(key: str, payload: dict) -> None:
    """Write payload to cache with current timestamp."""
    try:
        path = _cache_path(key)
        path.write_text(
            json.dumps({"_ts": time.time(), "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # non-fatal


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------

def make_check_key(
    repo: str,
    commit_hash: str,
    check_name: str,
    p_hash: str,
) -> str:
    """Build a stable cache key for a check result."""
    return f"{repo}::{commit_hash}::{check_name}::{p_hash}"


def policy_hash(checks_cfg: dict | None, excludes: list[str] | None) -> str:
    """Compute a short hash of the active policy (checks + excludes)."""
    payload = json.dumps(
        {"checks": checks_cfg or {}, "excludes": excludes or []},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
