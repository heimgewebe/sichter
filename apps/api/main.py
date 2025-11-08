"""FastAPI entry-point for the Sichter control plane."""
from __future__ import annotations

import heapq
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

try:  # optional
    import yaml  # type: ignore
except ModuleNotFoundError:
    yaml = None

from lib import simpleyaml

STATE = Path.home() / ".local/state/sichter"
QUEUE = STATE / "queue"
EVENTS = STATE / "events"
LOGS = STATE / "logs"
POLICY_PATH = Path.home() / ".config/sichter/policy.yml"
REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
_LOCK = threading.Lock()

for directory in (QUEUE, EVENTS, LOGS, POLICY_PATH.parent):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sichter API", version="0.2.0")

# --- simple rate limiter ---------------------------------------------------
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("SICHTER_RATE_LIMIT", "120"))
RATE_LIMIT_WINDOW_SECONDS = 60
_request_log: Dict[str, Deque[float]] = defaultdict(deque)


def rate_limiter(request: Request) -> None:
    """Simple fixed-window rate limiter per client host."""
    now = time.time()
    client = request.client.host if request.client else "unknown"
    with _LOCK:
        bucket = _request_log[client]

        while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="rate limit exceeded")

        bucket.append(now)


# --- helpers ----------------------------------------------------------------


def _timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _enqueue(job: Dict[str, Any]) -> str:
    job = dict(job)
    job.setdefault("ts", _timestamp())
    job.setdefault("job_id", f"{int(time.time())}-{uuid.uuid4().hex}")
    job_id = job["job_id"]
    (QUEUE / f"{job_id}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))
    _write_event({"type": "queue", "job_id": job_id, "payload": job})
    return job_id


def _write_event(event: Dict[str, Any]) -> None:
    payload = dict(event)
    payload.setdefault("ts", _timestamp())
    day_file = EVENTS / f"{payload['ts'][:10].replace('-', '')}.jsonl"
    try:
        with day_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        logging.exception("Failed to write API event to %s", day_file)


def _read_policy() -> Dict[str, Any]:
    if not POLICY_PATH.exists():
        return {}
    text = POLICY_PATH.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return simpleyaml.load(POLICY_PATH)


def _write_policy(values: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atomically overwrite policy.yml with structured YAML.

    This uses a temporary file and atomic rename to avoid race conditions
    and corruption.
    """
    try:
        if yaml is not None:
            text = yaml.safe_dump(values, sort_keys=False, allow_unicode=True)
        else:
            text = simpleyaml.dump(values)

        with _LOCK:
            # Create a temporary file in the same directory to ensure atomic move
            with tempfile.NamedTemporaryFile(
                "w",
                dir=POLICY_PATH.parent,
                encoding="utf-8",
                delete=False,
                prefix=f"{POLICY_PATH.name}-",
            ) as handle:
                handle.write(text)
                temp_path = Path(handle.name)
            # Atomically replace the original file with the new content
            temp_path.rename(POLICY_PATH)

    except (OSError, TypeError):
        logging.exception("Failed to write policy file to %s", POLICY_PATH)
        # Clean up the temporary file if the rename failed
        if "temp_path" in locals() and temp_path.exists():
            temp_path.unlink()
        raise

    _write_event({"type": "policy", "action": "write", "values": values})
    return values


# --- middleware -------------------------------------------------------------

raw_origins = os.environ.get("SICHTER_DASHBOARD_ORIGINS")
allowed_origins = (
    [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    if raw_origins
    else ["http://localhost:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- models -----------------------------------------------------------------


class EnqueuePayload(BaseModel):
    repo: str = Field(..., description="Repository name")
    mode: Literal["deep", "light", "changed", "all"] = Field(
        "changed", description="Requested inspection mode"
    )
    auto_pr: bool = Field(True, description="Whether automated PRs should be opened")


class SweepPayload(BaseModel):
    mode: Literal["all", "changed"] = Field(
        "changed", description="Scope of the sweep execution"
    )


class PolicyUpdate(BaseModel):
    values: Dict[str, Any]


# --- endpoints ---------------------------------------------------------------


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    """Liveness probe."""
    return "ok"


@app.get("/readyz")
def readyz() -> Dict[str, Any]:
    """Readiness probe ensuring state directories are reachable."""
    status = {
        "queue": QUEUE.is_dir(),
        "events": EVENTS.is_dir(),
        "logs": LOGS.is_dir(),
    }
    ready = all(status.values())
    if not ready:
        raise HTTPException(status_code=503, detail=status)
    return {"status": "ready", **status}


@app.post("/enqueue", dependencies=[Depends(rate_limiter)])
def enqueue(payload: EnqueuePayload) -> Dict[str, Any]:
    if not REPO_PATTERN.match(payload.repo):
        raise HTTPException(status_code=400, detail="Invalid repo name format")
    job = {
        "type": "repository",
        "mode": payload.mode,
        "repo": payload.repo,
        "auto_pr": payload.auto_pr,
    }
    job_id = _enqueue(job)
    return {"enqueued": job_id, "queued": job}


@app.get("/events/tail", response_class=PlainTextResponse)
def tail_events(
    n: int = 200,
    since: float | None = None,
    _: None = Depends(rate_limiter),
) -> str:
    """
    Return up to *n* newest events as JSONL, memory-efficiently.

    Parameters:
        n: Maximum number of events to return.
        since: If provided, only events with a timestamp greater than this value
            (seconds since epoch, UTC) will be returned.
    """
    files = sorted(EVENTS.glob("*.jsonl"), key=os.path.getmtime, reverse=True)
    heap = []

    for fp in files:
        if since and fp.stat().st_mtime < since:
            continue
        try:
            with fp.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                        ts_str = event.get("ts")
                        if not ts_str:
                            continue
                        ts = datetime.fromisoformat(ts_str).timestamp()
                        if since and ts < since:
                            continue
                        item = (ts, uuid.uuid4().hex, event)
                        if len(heap) < n:
                            heapq.heappush(heap, item)
                        elif ts > heap[0][0]:
                            heapq.heapreplace(heap, item)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue
        except OSError:
            logging.warning("Could not process event file %s", fp)
            continue

    sorted_events = sorted([item[2] for item in heap], key=lambda e: e["ts"], reverse=True)
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in sorted_events)


@app.get("/policy")
def read_policy(_: None = Depends(rate_limiter)) -> Dict[str, Any]:
    return {"path": str(POLICY_PATH), "values": _read_policy()}


@app.put("/policy")
def write_policy(update: PolicyUpdate, _: None = Depends(rate_limiter)) -> Dict[str, Any]:
    values = _write_policy(update.values)
    return {"path": str(POLICY_PATH), "values": values}


@app.get("/logs/latest", response_class=PlainTextResponse)
def latest_log(_: None = Depends(rate_limiter)) -> str:
    """Convenience endpoint to fetch the newest log snippet."""
    files = sorted(LOGS.glob("*.log"), key=os.path.getmtime, reverse=True)
    if not files:
        return ""
    latest = files[0]
    try:
        return latest.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=500, detail=f"failed to read log: {latest}")


@app.post("/sweep", dependencies=[Depends(rate_limiter)])
def sweep(payload: SweepPayload) -> Dict[str, Any]:
    job = {
        "type": "sweep",
        "mode": payload.mode,
    }
    job_id = _enqueue(job)
    return {"enqueued": job_id, "queued": job}
