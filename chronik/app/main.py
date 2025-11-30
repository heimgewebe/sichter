import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_ROOT = Path(__file__).resolve().parent
# Standard: Sichter-Layout
STATE_ROOT = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
QUEUE_DIR = STATE_ROOT / "sichter/queue"
EVENTS_DIR = STATE_ROOT / "sichter/events"
REVIEW_ROOT = Path(os.environ.get("REVIEW_ROOT", str(Path.home() / "sichter" / "review")))
INDEX = REVIEW_ROOT / "index.json"

app = FastAPI(title="Sichter Chronik", version="0.1.0")

@app.on_event("startup")
async def startup_event():
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)


def is_valid_jid(jid: str):
    return len(jid) > 8 and all(c in "abcdef0123456789-" for c in jid)

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/api/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat(timespec="seconds")+"Z"}

def load_index():
    if not INDEX.exists():
        return {"repos": []}
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"repos": data}
    except Exception as e:
        raise HTTPException(500, f"index.json unreadable: {e}") from e

def collect_repo_report(repo_dir: Path):
    report = repo_dir / "report.json"
    if report.exists():
        try:
            return json.loads(report.read_text(encoding="utf-8"))
        except Exception:
            return {"error": "report.json parse error"}
    jsons = sorted(repo_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if jsons:
        try:
            return json.loads(jsons[0].read_text(encoding="utf-8"))
        except Exception:
            return {"error": f"{jsons[0].name} parse error"}
    return {}

@app.get("/api/summary")
def summary():
    idx = load_index()
    repos = idx.get("repos", [])
    total = len(repos)
    errors = critical = warning = 0

    for r in repos:
        name = r.get("name") or r.get("repo") or "unknown"
        rep = collect_repo_report(REVIEW_ROOT / name)
        sev = (rep.get("severity") or rep.get("level") or "").lower()
        findings = rep.get("findings") or rep.get("issues") or []
        if sev == "critical":
            critical += 1
            errors += 1
        elif sev in ("error","high"):
            errors += 1
        elif sev in ("warn","warning","medium"):
            warning += 1
        elif isinstance(findings, list) and findings:
            warning += 1
    return {
        "total_repos": total,
        "errors": errors,
        "critical": critical,
        "warnings": warning,
        "timestamp": datetime.utcnow().isoformat(timespec="seconds")+"Z",
    }

@app.get("/api/repos")
def api_repos():
    idx = load_index()
    out = []
    for r in idx.get("repos", []):
        name = r.get("name") or r.get("repo") or "unknown"
        repo_dir = REVIEW_ROOT / name
        rep = collect_repo_report(repo_dir)
        updated = None
        try:
            mt = max([p.stat().st_mtime for p in repo_dir.glob("*.json")], default=0)
            if mt:
                updated = datetime.utcfromtimestamp(mt).isoformat(timespec="seconds")+"Z"
        except Exception:
            pass
        sev = (rep.get("severity") or rep.get("level") or "").lower() or ("warning" if rep else "ok")
        out.append({"name": name, "severity": sev, "updated": updated, "snapshot": rep})
    return {"items": out}

@app.get("/api/report/{repo}")
def api_report(repo: str):
    # Validate: repo name must not contain path separators or traversal
    import re
    INVALID = re.compile(r"[\\/]|^\.\.?$|^$")
    if INVALID.search(repo):
        raise HTTPException(403, "Invalid repo name")
    repo_dir = (REVIEW_ROOT / repo).resolve()
    try:
        repo_dir.relative_to(REVIEW_ROOT.resolve())
    except ValueError as e:
        raise HTTPException(403, "Invalid repo path") from e
    if not repo_dir.exists():
        raise HTTPException(404, "repo not found")
    rep = collect_repo_report(repo_dir)
    return rep or {}

def _collect_events(n=100):
    if not EVENTS_DIR.exists():
        return []

    # both json and jsonl are supported
    files = sorted(EVENTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    files.extend(sorted(EVENTS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True))

    events = []
    for f in files:
        if len(events) >= n:
            break
        try:
            if f.suffix == ".jsonl":
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line:
                        events.append(json.loads(line))
            else:
                events.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass # ignore parse errors on best-effort basis
    return events[:n]

@app.get("/api/events/recent")
def events_recent(n: int = 100):
    return _collect_events(n)

@app.post("/api/jobs/submit")
async def job_submit(req: Request):
    try:
        payload = await req.json()
    except Exception as e:
        raise HTTPException(400, "invalid json") from e
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(400, "invalid payload")
    jid = str(uuid.uuid4())
    data = {
        "id": jid,
        "submitted_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "payload": payload,
        "status": "pending",
    }
    try:
        (QUEUE_DIR / f"{jid}.json.new").write_text(json.dumps(data, indent=2), encoding="utf-8")
        (QUEUE_DIR / f"{jid}.json.new").rename(QUEUE_DIR / f"{jid}.json")
    except OSError as e:
        raise HTTPException(500, f"failed to write job to queue: {e}") from e
    return JSONResponse({"enqueued": jid, "status_url": f"/api/jobs/{jid}"}, 202)

app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")

@app.get("/")
def root():
    index = APP_ROOT / "static" / "index.html"
    if not index.exists():
        raise HTTPException(500, "index.html missing")
    return FileResponse(str(index))
