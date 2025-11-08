# apps/api/main.py
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import json, time, uuid, os, subprocess

STATE = Path.home()/".local/state/sichter"
QUEUE = STATE/"queue"
EVENTS = STATE/"events"
LOGS  = STATE/"logs"
for p in (QUEUE, EVENTS, LOGS):
    p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sichter API", version="0.1.1")
# CORS für Dashboard (Vite etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Job(BaseModel):
    type: str              # "ScanAll" | "ScanChanged" | "PRSweep"
    mode: str = "changed"  # "all" | "changed"
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

def _systemctl_show(service: str) -> dict[str, str]:
    try:
        env = dict(os.environ)
        env["SYSTEMD_PAGER"] = ""
        raw = subprocess.check_output(
            ["systemctl", "--user", "show", service, "--property", "ActiveState,SubState,ExecMainStartTimestamp,ActiveEnterTimestamp,InactiveExitTimestamp,MainPID"],
            text=True,
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError):
        return {}
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def _parse_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    # systemd liefert menschenlesbare Strings; ohne Format robust nicht parsbar.
    # Gib den Originalwert zurück, aber fang alle Fehler ab.
    # Versuche nichts zu parsen, reiche roh durch:
    return value


def _queue_state(limit: int = 10) -> dict:
    items = []
    for fp in sorted(QUEUE.glob("*.json"), key=os.path.getmtime):
        try:
            payload = json.loads(fp.read_text())
        except (OSError, json.JSONDecodeError):
            payload = {}
        items.append(
            {
                "id": fp.stem,
                "path": str(fp),
                "type": payload.get("type"),
                "mode": payload.get("mode"),
                "repo": payload.get("repo"),
                "enqueuedAt": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(),
            }
        )
    return {
        "size": len(items),
        "items": items[-limit:],
    }


def _collect_events(limit: int = 200) -> list[dict[str, str | dict]]:
    # Bevorzuge .jsonl (neues Format), fallback .log (alt)
    # Erst alle Dateien sammeln, dann die Zeilen limitieren. Sonst werden
    # die neuesten Events ggf. verworfen.
    files = sorted(EVENTS.glob("*.jsonl"), key=os.path.getmtime, reverse=True)
    if not files:
        files = sorted(EVENTS.glob("*.log"), key=os.path.getmtime, reverse=True)
    lines: list[str] = []
    for fp in files:
        try:
            lines.extend(fp.read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            continue
    events: list[dict[str, str | dict]] = []
    for raw in lines[-limit:]:
        entry: dict[str, str | dict] = {"line": raw}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            entry["payload"] = data
            entry["ts"] = data.get("ts") or data.get("payload", {}).get("ts")
            entry["kind"] = data.get("event") or data.get("kind")
        events.append(entry)
    return events


def _policy_path() -> Path:
    return Path.home() / ".config/sichter/policy.yml"


def _read_policy() -> dict:
    policy_file = _policy_path()
    candidates = [policy_file]
    repo_policy = Path(__file__).resolve().parent.parent.parent / "config" / "policy.yml"
    if repo_policy not in candidates:
        candidates.append(repo_policy)
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            return {"path": str(candidate), "content": candidate.read_text()}
        except OSError:
            continue
    return {"path": str(policy_file), "content": ""}


def _resolve_repos() -> list[str]:
    repos: list[str] = []
    local_policy = Path(__file__).resolve().parent.parent.parent / "config" / "policy.yml"
    if local_policy.exists():
        try:
            for line in local_policy.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                if stripped.startswith("allowlist:") and "[]" in stripped:
                    repos.clear()
                    break
                if stripped.startswith("-"):
                    candidate = stripped.split("-", 1)[1].strip()
                    if candidate:
                        repos.append(candidate)
        except OSError:
            repos = []
    if repos:
        return repos
    org = os.environ.get("HAUSKI_ORG")
    remote_base = os.environ.get("HAUSKI_REMOTE_BASE")
    if org and remote_base:
        base = Path(os.path.expandvars(remote_base)).expanduser()
        if base.exists():
            repos = [f"{org}/{entry.name}" for entry in base.iterdir() if entry.is_dir()]
    if not repos:
        repo = os.environ.get("GITHUB_REPOSITORY")
        if repo:
            repos = [repo]
    return sorted(repos)


@app.get("/events/tail", response_class=PlainTextResponse)
def tail_events(n: int = 200):
    events = _collect_events(n)
    return "\n".join(entry.get("line", "") for entry in events if entry.get("line"))


@app.get("/events/recent")
def recent_events(n: int = 200):
    return {"events": _collect_events(n)}


@app.get("/overview")
def overview():
    worker = _systemctl_show("sichter-worker.service")
    return {
        "worker": {
            "activeState": worker.get("ActiveState", "unknown"),
            "subState": worker.get("SubState", "unknown"),
            "mainPID": worker.get("MainPID"),
            "since": _parse_timestamp(worker.get("ActiveEnterTimestamp") or worker.get("ExecMainStartTimestamp")),
            "lastExit": _parse_timestamp(worker.get("InactiveExitTimestamp")),
        },
        "queue": _queue_state(),
        "events": _collect_events(50),
    }


@app.get("/repos/status")
def repos_status():
    repos = _resolve_repos()
    events = _collect_events(200)
    results: list[dict] = []
    for repo in repos:
        latest = next((evt for evt in reversed(events) if repo in json.dumps(evt, ensure_ascii=False)), None)
        results.append(
            {
                "name": repo,
                "lastEvent": latest,
            }
        )
    return {"repos": results}

import tempfile
@app.post("/settings/policy")
def write_policy(content: dict = Body(...)):
    # stores to ~/.config/sichter/policy.yml
    cfg = Path.home()/".config/sichter"
    cfg.mkdir(parents=True, exist_ok=True)
    target = cfg/"policy.yml"
    raw = content.get("raw") if isinstance(content, dict) else None
    if isinstance(raw, str) and raw.strip():
        text = raw if raw.endswith("\n") else raw + "\n"
    else:
        lines = [f"{k}: {v}" for k, v in content.items()]
        text = "\n".join(lines) + ("\n" if lines else "")

    # Atomares Schreiben: In temporäre Datei schreiben, dann verschieben
    # um korrupte policy.yml zu vermeiden, wenn der Schreibvorgang
    # unterbrochen wird.
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=cfg, prefix=".policy.yml.tmp-")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.rename(tmp_path, target)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return {"written": str(target)}


@app.get("/settings/policy")
def read_policy():
    return _read_policy()
