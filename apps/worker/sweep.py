from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try: # pragma: no cover - optional dependency
 import yaml
except ModuleNotFoundError: # pragma: no cover
 yaml = None

from lib import simpleyaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config/policy.yml"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "sichter"
QUEUE_DIR = STATE_DIR / "queue"
EVENT_DIR = STATE_DIR / "events"
LOG_DIR = Path.home() / "sichter/logs"

QUEUE_DIR.mkdir(parents=True, exist_ok=True)
EVENT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def read_policy(path: Path) -> dict:
 if yaml is not None:
  with path.open("r", encoding="utf-8") as handle:
   return yaml.safe_load(handle) or {}
 return simpleyaml.load(path)


def resolve_policy(path: str | None) -> dict:
 if path:
  return read_policy(Path(path))
 config_path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "sichter/policy.yml"
 if config_path.exists():
  return read_policy(config_path)
 return read_policy(DEFAULT_POLICY)


def write_job(policy: dict, mode: str, repo: str | None) -> Path:
 job_type = "ScanAll" if mode == "all" else "ScanChanged"
 now = datetime.now(timezone.utc)
 payload = {
  "type": job_type,
  "mode": mode,
  "org": policy.get("org", "heimgewebe"),
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
