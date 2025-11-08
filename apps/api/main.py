# apps/api/main.py
from fastapi import FastAPI, Body
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pathlib import Path
import json, time, uuid, os

try: # pragma: no cover
 import yaml
except ModuleNotFoundError: # pragma: no cover
 yaml = None

from lib import simpleyaml

STATE = Path.home()/".local/state/sichter"
QUEUE = STATE/"queue"
EVENTS = STATE/"events"
LOGS = STATE/"logs"
for p in (QUEUE, EVENTS, LOGS): p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sichter API", version="0.1.0")

class Job(BaseModel):
    type: str # "ScanAll" | "ScanChanged" | "PRSweep"
    mode: str = "changed" # "all" | "changed"
    org: str = "heimgewebe"
    repo: str | None = None
    auto_pr: bool = True

def _enqueue(job: dict) -> str:
    jid = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    f = (QUEUE/f"{jid}.json")
    f.write_text(json.dumps(job, ensure_ascii=False, indent=2))
    return jid

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"

@app.post("/jobs/submit")
def submit(job: Job):
    jid = _enqueue(job.model_dump())
    return {"enqueued": jid, "queue_dir": str(QUEUE)}

@app.get("/events/tail", response_class=PlainTextResponse)
def tail_events(n: int = 200):
    # concat newest event files (very simple)
    files = sorted(EVENTS.glob("*.jsonl"), key=os.path.getmtime, reverse=True)[:3]
    lines = []
    for fp in files:
        try:
            lines += fp.read_text().splitlines()[-n:]
        except (OSError, UnicodeDecodeError) as e:
            # Skip files that cannot be read or decoded; continue with others.
            pass
    return "\n".join(lines)

@app.post("/settings/policy")
def write_policy(content: dict = Body(...)):
    # stores to ~/.config/sichter/policy.yml
    cfg = Path.home()/".config/sichter"
    cfg.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        text = yaml.safe_dump(content, sort_keys=False, allow_unicode=True)
    else:
        text = simpleyaml.dump(content)
    (cfg/"policy.yml").write_text(text)
    return {"written": str(cfg/"policy.yml")}
