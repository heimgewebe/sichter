import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_ROOT = Path(__file__).resolve().parent

class Settings:
    def __init__(self, state_root: Optional[Path] = None, review_root: Optional[Path] = None):
        self.state_root = state_root or Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        self.review_root = review_root or Path(os.environ.get("REVIEW_ROOT", str(Path.home() / "sichter" / "review")))

        # Derived paths
        self.queue_dir = self.state_root / "sichter/queue"
        self.events_dir = self.state_root / "sichter/events"
        self.index = self.review_root / "index.json"

@lru_cache()
def get_settings():
    return Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    settings.queue_dir.mkdir(parents=True, exist_ok=True)
    settings.events_dir.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown (nothing to do here)


app = FastAPI(title="Sichter Chronik", version="0.1.0", lifespan=lifespan)


def is_valid_jid(jid: str):
    return len(jid) > 8 and all(c in "abcdef0123456789-" for c in jid)

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/api/health")
def health():
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")+"Z"}

def load_index(settings: Settings):
    if not settings.index.exists():
        return {"repos": []}
    try:
        data = json.loads(settings.index.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"repos": data}
    except Exception as e:
        raise HTTPException(500, f"index.json unreadable: {e}") from e

def collect_repo_report(repo_dir: Path):
    report = repo_dir / "report.json"
    if report.exists():
        try:
            return json.loads(report.read_text(encoding="utf-8")), report.stat().st_mtime
        except Exception:
            return {"error": "report.json parse error"}, 0
    try:
        # Find newest json file by mtime.
        # Use a generator to perform stat() only once per file.
        newest_entry = max(
            ((p.stat().st_mtime, p) for p in repo_dir.glob("*.json")),
            default=None
        )
        if newest_entry:
            mtime, newest = newest_entry
            try:
                return json.loads(newest.read_text(encoding="utf-8")), mtime
            except Exception:
                return {"error": f"{newest.name} parse error"}, 0
    except OSError:
        # Ignore filesystem errors (e.g. permission denied)
        pass
    return {}, 0

@app.get("/api/summary")
def summary(settings: Settings = Depends(get_settings)):
    idx = load_index(settings)
    repos = idx.get("repos", [])
    total = len(repos)
    errors = critical = warning = 0

    for r in repos:
        name = r.get("name") or r.get("repo") or "unknown"
        rep, _ = collect_repo_report(settings.review_root / name)
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
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")+"Z",
    }

@app.get("/api/repos")
def api_repos(settings: Settings = Depends(get_settings)):
    idx = load_index(settings)
    out = []
    for r in idx.get("repos", []):
        name = r.get("name") or r.get("repo") or "unknown"
        repo_dir = settings.review_root / name
        rep, mt = collect_repo_report(repo_dir)
        updated = None
        if mt:
            updated = datetime.fromtimestamp(mt, tz=timezone.utc).isoformat(timespec="seconds")+"Z"
        sev = (rep.get("severity") or rep.get("level") or "").lower() or ("warning" if rep else "ok")
        out.append({"name": name, "severity": sev, "updated": updated, "snapshot": rep})
    return {"items": out}

@app.get("/api/report/{repo}")
def api_report(repo: str, settings: Settings = Depends(get_settings)):
    # Validate: repo name must not contain path separators or traversal
    import re
    INVALID = re.compile(r"[\\/]|^\.\.?$|^$")
    if INVALID.search(repo):
        raise HTTPException(403, "Invalid repo name")
    repo_dir = (settings.review_root / repo).resolve()
    try:
        repo_dir.relative_to(settings.review_root.resolve())
    except ValueError as e:
        raise HTTPException(403, "Invalid repo path") from e
    if not repo_dir.exists():
        raise HTTPException(404, "repo not found")
    rep, _ = collect_repo_report(repo_dir)
    return rep or {}

def _collect_events(settings: Settings, n=100):
    if not settings.events_dir.exists():
        return []

    # both json and jsonl are supported
    files = sorted(settings.events_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    files.extend(sorted(settings.events_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True))

    events = []
    for f in files:
        if len(events) >= n:
            break
        try:
            if f.suffix == ".jsonl":
                with f.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            events.append(json.loads(line))
                            if len(events) >= n:
                                break
            else:
                events.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass # ignore parse errors on best-effort basis
    return events[:n]

@app.get("/api/events/recent")
def events_recent(n: int = 100, settings: Settings = Depends(get_settings)):
    return _collect_events(settings, n)

@app.post("/api/jobs/submit")
async def job_submit(req: Request, settings: Settings = Depends(get_settings)):
    try:
        payload = await req.json()
    except Exception as e:
        raise HTTPException(400, "invalid json") from e
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(400, "invalid payload")
    jid = str(uuid.uuid4())
    data = {
        "id": jid,
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "payload": payload,
        "status": "pending",
    }
    try:
        (settings.queue_dir / f"{jid}.json.new").write_text(json.dumps(data, indent=2), encoding="utf-8")
        (settings.queue_dir / f"{jid}.json.new").rename(settings.queue_dir / f"{jid}.json")
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
