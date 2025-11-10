from __future__ import annotations
import json, os, time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "sichter"
QUEUE = STATE / "queue"
EVENTS = STATE / "events"
QUEUE.mkdir(parents=True, exist_ok=True)
EVENTS.mkdir(parents=True, exist_ok=True)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def append_event(event: dict) -> None:
    path = EVENTS / f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), **event}, ensure_ascii=False) + "\n")

def main() -> int:
    print("[stub] waiting for a job in", QUEUE, flush=True)
    deadline = time.time() + 30
    jobfile = None
    while time.time() < deadline and not jobfile:
        candidates = sorted(QUEUE.glob("*.json"))
        if candidates:
            jobfile = candidates[0]
            break
        time.sleep(0.2)
    if not jobfile:
        print("[stub] no job found within timeout", flush=True)
        return 1
    try:
        payload = json.loads(jobfile.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    job_id = jobfile.stem
    append_event({"type":"stub-consume","job_id": job_id, "payload": payload})
    try:
        jobfile.unlink(missing_ok=True)
    except Exception:
        pass
    print("[stub] processed job", job_id, flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
