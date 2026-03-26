"""Result cache for repository checks."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "sichter"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def _path_for_key(key: str) -> Path:
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  return CACHE_DIR / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"


def cache_get(key: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict | None:
  path = _path_for_key(key)
  if not path.exists():
    return None
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return None
  if time.time() - float(data.get("_ts", 0)) > ttl_seconds:
    path.unlink(missing_ok=True)
    return None
  payload = data.get("payload")
  return payload if isinstance(payload, dict) else None


def cache_set(key: str, payload: dict) -> None:
  path = _path_for_key(key)
  try:
    path.write_text(
      json.dumps({"_ts": time.time(), "payload": payload}, ensure_ascii=False),
      encoding="utf-8",
    )
  except OSError:
    return


def make_check_key(repo: str, commit_hash: str, check_name: str, policy_hash: str) -> str:
  return f"{repo}::{commit_hash}::{check_name}::{policy_hash}"


def policy_hash(checks_cfg: dict | None, excludes: list[str] | None) -> str:
  payload = json.dumps({"checks": checks_cfg or {}, "excludes": excludes or []}, sort_keys=True)
  return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
