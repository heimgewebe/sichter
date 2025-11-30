from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.config import (
    DEFAULT_ORG,
    EVENTS,
    QUEUE,
    ensure_directories,
    get_policy_path,
    load_yaml,
)

ROOT = Path(__file__).resolve().parents[2]
QUEUE_DIR = QUEUE
EVENT_DIR = EVENTS
LOG_DIR = Path.home() / "sichter/logs"

ensure_directories()
LOG_DIR.mkdir(parents=True, exist_ok=True)


def resolve_policy(path: str | None) -> dict:
 if path:
  return load_yaml(Path(path))
 policy_path = get_policy_path()
 return load_yaml(policy_path) if policy_path.exists() else {}


def write_job(policy: dict, mode: str, repo: str | None) -> Path:
 job_type = "ScanAll" if mode == "all" else "ScanChanged"
 now = datetime.now(timezone.utc)
 payload = {
  "type": job_type,
  "mode": mode,
  "org": policy.get("org", DEFAULT_ORG),
  "repo": repo,
  "auto_pr": bool(policy.get("auto_pr", True)),
  "timestamp": now.isoformat(),
 }
 job_file = QUEUE_DIR / f"{int(now.timestamp())}-{uuid.uuid4().hex}.json"
 job_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
 return job_file


def append_event(message: str, payload: dict | None = None) -> None:
 now = datetime.now(timezone.utc)
 event_file = EVENT_DIR / f"sweep-{now.strftime('%Y%m%d')}.jsonl"
 record = {
  "ts": now.isoformat(),
  "message": message,
  "payload": payload or {},
 }
 with event_file.open("a", encoding="utf-8") as handle:
  handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_post_hook() -> None:
 hook = ROOT / "hooks/post-run"
 if hook.exists():
  os.environ.setdefault("SICHTER_REPO_ROOT", str(ROOT))
  try:
   import subprocess
   subprocess.run([str(hook)], check=False)
  except Exception:
   # Hook ist optional – niemals den Sweep crashen lassen
   pass


def main(argv: list[str] | None = None) -> int:
 parser = argparse.ArgumentParser(description="Sichter Sweep CLI")
 parser.add_argument("--mode", choices=["all", "changed"], default="changed")
 parser.add_argument("--policy")
 parser.add_argument("--repo")
 args, extras = parser.parse_known_args(argv)

 policy = resolve_policy(args.policy)

 job_file = write_job(policy, args.mode, args.repo)

 summary = {
  "job_file": str(job_file),
  "mode": args.mode,
  "org": policy.get("org"),
  "auto_pr": bool(policy.get("auto_pr", True)),
  "extra_args": extras,
 }
 print(json.dumps(summary, indent=2, ensure_ascii=False))

 append_event("sweep_enqueued", summary)
 run_post_hook()
 return 0


if __name__ == "__main__": # pragma: no cover
 sys.exit(main())
