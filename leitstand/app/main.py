from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime
import json, os

APP_ROOT = Path(__file__).resolve().parent
# Standard: Sichter-Layout
REVIEW_ROOT = Path(os.environ.get("REVIEW_ROOT", str(Path.home() / "sichter" / "review")))
INDEX = REVIEW_ROOT / "index.json"

app = FastAPI(title="Sichter Leitstand", version="0.1.0")

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
        raise HTTPException(500, f"index.json unreadable: {e}")

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
        else:
            if isinstance(findings, list) and findings:
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
            if mt: updated = datetime.utcfromtimestamp(mt).isoformat(timespec="seconds")+"Z"
        except Exception:
            pass
        sev = (rep.get("severity") or rep.get("level") or "").lower() or ("warning" if rep else "ok")
        out.append({"name": name, "severity": sev, "updated": updated, "snapshot": rep})
    return {"items": out}

@app.get("/api/report/{repo}")
def api_report(repo: str):
    # Safely resolve repo directory path and prevent traversal or external access
    # Reject absolute paths and path separators to enforce name-only repo selection
    if Path(repo).is_absolute() or ".." in repo or "/" in repo or "\\" in repo:
        raise HTTPException(400, "Invalid repo name")
    try:
        repo_dir = (REVIEW_ROOT / repo).resolve()
        # Ensure repo_dir is a subdirectory of REVIEW_ROOT
        repo_dir.relative_to(REVIEW_ROOT)
    except (ValueError, RuntimeError):
        raise HTTPException(400, "Invalid repo path")
    if not repo_dir.exists():
        raise HTTPException(404, "repo not found")
    rep = collect_repo_report(repo_dir)
    return rep or {}

app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")

@app.get("/")
def root():
    index = APP_ROOT / "static" / "index.html"
    if not index.exists():
        raise HTTPException(500, "index.html missing")
    return FileResponse(str(index))
