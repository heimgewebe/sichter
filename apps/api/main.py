# apps/api/main.py
import errno
import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from lib.config import CONFIG, EVENTS, QUEUE, ensure_directories, get_policy_path, load_yaml

ensure_directories()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sichter.api")

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
  type: str  # "ScanAll" | "ScanChanged" | "PRSweep"
  mode: str = "changed"  # "all" | "changed"
  org: str = "heimgewebe"  # Keep default for backward compatibility
  repo: str | None = None
  auto_pr: bool = True


class JobSubmitResponse(BaseModel):
  enqueued: str
  queue_dir: str


class ErrorDetail(BaseModel):
  error: str
  code: str | None = None
  retryable: bool | None = None


class ErrorResponse(BaseModel):
  detail: ErrorDetail


def _enqueue(job: dict) -> str:
  jid = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
  f = QUEUE / f"{jid}.json"
  try:
    f.write_text(json.dumps(job, ensure_ascii=False, indent=2))
  except OSError as e:
    logger.error(f"Failed to enqueue job: {e}")
    raise
  return jid


def _timestamp() -> str:
  return datetime.now(timezone.utc).isoformat()


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
  return "ok"


@app.post("/jobs/submit", response_model=JobSubmitResponse, responses={500: {"model": ErrorResponse}})
def submit(job: Job) -> JobSubmitResponse:
  try:
    jid = _enqueue(job.model_dump())
    return JobSubmitResponse(enqueued=jid, queue_dir=str(QUEUE))
  except OSError as exc:
    logger.exception("Error submitting job.")
    non_retryable_errnos = {errno.EPERM, errno.EACCES, errno.EROFS, errno.ENOSPC}
    retryable = exc.errno is not None and exc.errno not in non_retryable_errnos
    raise HTTPException(
      status_code=500,
      detail={
        "error": "Internal server error",
        "code": "ENQUEUE_FAILED",
        "retryable": retryable,
      },
    )


def _systemctl_show(service: str) -> dict[str, str]:
  try:
    env = dict(os.environ)
    env["SYSTEMD_PAGER"] = ""
    raw = subprocess.check_output(
      [
        "systemctl",
        "--user",
        "show",
        service,
        "--property",
        "ActiveState,SubState,ExecMainStartTimestamp,ActiveEnterTimestamp,InactiveExitTimestamp,MainPID",
      ],
      text=True,
      env=env,
    )
  except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
    logger.debug(f"systemctl show failed for {service}: {e}")
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


def _queue_state(limit: int = 10) -> dict[str, int | list[dict]]:
  """Get current queue state with most recent jobs.

  Args:
    limit: Maximum number of queue items to return

  Returns:
    Dictionary with queue size and recent items
  """
  # Collect all queue files first for counting
  all_files = list(QUEUE.glob("*.json"))
  total_size = len(all_files)

  # Sort only if needed and get the most recent ones
  if total_size == 0:
    return {"size": 0, "items": []}

  # Sort files by modification time (oldest first) and take last N
  all_files.sort(key=os.path.getmtime)
  recent_files = all_files[-limit:] if total_size > limit else all_files

  # Build items in chronological order (oldest to newest)
  items: list[dict] = []
  for fp in recent_files:
    try:
      payload = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
      logger.warning(f"Failed to read/parse queue file {fp}: {e}")
      payload = {}
    items.append(
      {
        "id": fp.stem,
        "path": str(fp),
        "type": payload.get("type"),
        "mode": payload.get("mode"),
        "repo": payload.get("repo"),
        "enqueuedAt": datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc).isoformat(),
      }
    )

  return {
    "size": total_size,
    "items": items,
  }


def _tail_file(path: Path, n: int, block_size: int = 4096) -> list[str]:
  """Read the last n lines from a file without loading the entire file."""
  try:
    with path.open("rb") as f:
      f.seek(0, os.SEEK_END)
      file_size = f.tell()

      if file_size == 0:
        return []

      data = b""
      # We want to find at least n+1 newlines to get n lines
      # (the last line might not end with newline, but usually logs do)

      # Read from end
      for pos in range(file_size, -1, -block_size):
          seek_pos = max(0, pos - block_size)
          read_len = pos - seek_pos
          f.seek(seek_pos)
          chunk = f.read(read_len)
          data = chunk + data
          if data.count(b'\n') >= n + 1:
              break
          if seek_pos == 0:
              break

      # Convert to text
      # Note: errors="ignore" might drop characters at block boundaries if they are multi-byte
      text = data.decode("utf-8", errors="ignore")
      lines = text.splitlines()

      # Return last n lines
      return lines[-n:]
  except OSError as e:
    logger.error(f"Failed to tail file {path}: {e}")
    return []


def _collect_events(limit: int = 200) -> list[dict[str, str | dict]]:
  """Collect recent events efficiently by reading from newest files first.

  Args:
    limit: Maximum number of events to collect

  Returns:
    List of event dictionaries with metadata
  """
  # Prefer .jsonl (new format), fallback to .log (old)
  files = sorted(EVENTS.glob("*.jsonl"), key=os.path.getmtime, reverse=True)
  if not files:
    files = sorted(EVENTS.glob("*.log"), key=os.path.getmtime, reverse=True)

  # Collect lines from newest files first until we have enough
  lines: list[str] = []
  for fp in files:
    # We need 'limit' lines total.
    needed = limit - len(lines)
    if needed <= 0:
        break

    file_lines = _tail_file(fp, needed)
    # _tail_file returns lines in chronological order (old -> new)
    # The existing logic expects 'lines' to store the newest lines first (descending order).
    # This allows correctly picking the 'limit' most recent lines across multiple files.
    lines.extend(reversed(file_lines))

  # Take most recent lines and reverse back to chronological order for display
  recent_lines = list(reversed(lines[:limit]))

  events: list[dict[str, str | dict]] = []
  for raw in recent_lines:
    if not raw.strip():
      continue
    entry: dict[str, str | dict] = {"line": raw}
    try:
      data = json.loads(raw)
      if isinstance(data, dict):
        entry["payload"] = data
        entry["ts"] = data.get("ts") or data.get("payload", {}).get("ts")
        entry["kind"] = data.get("event") or data.get("kind")
    except json.JSONDecodeError:
      pass
    events.append(entry)
  return events


def _read_policy() -> dict:
  policy_path = get_policy_path()
  try:
    return {"path": str(policy_path), "content": policy_path.read_text()}
  except OSError as e:
    logger.error(f"Failed to read policy from {policy_path}: {e}")
    return {"path": str(policy_path), "content": ""}


def _resolve_repos() -> list[str]:
  """Resolve list of repositories from policy or environment.

  Returns:
    Sorted list of repository names
  """
  repos: list[str] = []

  # Try to load from policy file
  try:
    policy_path = get_policy_path()
    if policy_path.exists():
      policy_data = load_yaml(policy_path)
      allowlist = policy_data.get("allowlist")
      if isinstance(allowlist, list):
        repos = [str(repo) for repo in allowlist if repo]
        if repos:
          return sorted(repos)
  except (OSError, ValueError) as e:
    logger.warning(f"Failed to load repos from policy: {e}")

  # Fallback to environment-based discovery
  org = os.environ.get("HAUSKI_ORG")
  remote_base = os.environ.get("HAUSKI_REMOTE_BASE")
  if org and remote_base:
    try:
      base = Path(os.path.expandvars(remote_base)).expanduser()
      if base.exists() and base.is_dir():
        repos = [f"{org}/{entry.name}" for entry in base.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")]
    except OSError as e:
      logger.warning(f"Failed to discover repos in {remote_base}: {e}")

  # Last resort: single repo from environment
  if not repos:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
      repos = [repo]

  return sorted(repos)


@app.get("/events/tail", response_class=PlainTextResponse)
def tail_events(n: int = 200) -> str:
  events = _collect_events(n)
  return "\n".join(entry.get("line", "") for entry in events if entry.get("line"))


@app.get("/events/recent")
def recent_events(n: int = 200) -> dict[str, list]:
  return {"events": _collect_events(n)}


@app.get("/overview")
def overview() -> dict:
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
def repos_status() -> dict[str, list[dict]]:
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


@app.post("/settings/policy")
def write_policy(content: Annotated[dict, Body()]) -> dict[str, str]:
  # stores to ~/.config/sichter/policy.yml
  CONFIG.mkdir(parents=True, exist_ok=True)
  target = CONFIG / "policy.yml"
  raw = content.get("raw") if isinstance(content, dict) else None
  if isinstance(raw, str) and raw.strip():
    text = raw if raw.endswith("\n") else raw + "\n"
  else:
    # Use PyYAML to dump safely
    text = yaml.dump(content, default_flow_style=False, allow_unicode=True)

  # Atomares Schreiben: In temporäre Datei schreiben, dann verschieben
  # um korrupte policy.yml zu vermeiden, wenn der Schreibvorgang
  # unterbrochen wird.
  tmp_path = None
  try:
    fd, tmp_path = tempfile.mkstemp(dir=CONFIG, prefix=".policy.yml.tmp-")
    with os.fdopen(fd, "w") as f:
      f.write(text)
    os.rename(tmp_path, str(target))
  except OSError as e:
    logger.error(f"Failed to write policy: {e}")
    if tmp_path and os.path.exists(tmp_path):
      os.unlink(tmp_path)
    raise
  finally:
    # Normally cleanup is handled, but if rename failed and we caught it, we handled it.
    # If rename succeeded, tmp_path is gone.
    # If os.fdopen failed, tmp_path exists and needs cleanup.
    if tmp_path and os.path.exists(tmp_path):
       # This might happen if os.rename fails and we raised exception,
       # or if we are in the 'finally' block after a success but 'rename' works atomically?
       # Actually os.rename removes the source.
       # So this is for the case where something failed BEFORE rename.
       try:
         os.unlink(tmp_path)
       except OSError:
         pass

  return {"written": str(target)}


@app.get("/settings/policy")
def read_policy() -> dict[str, str]:
  return _read_policy()


# --- websocket: /events/stream ------------------------------------------------


def _jsonl_files() -> list[Path]:
  """Return jsonl event files sorted by mtime ascending."""
  return sorted(EVENTS.glob("*.jsonl"), key=os.path.getmtime)


def _read_last_lines(path: Path, n: int) -> list[str]:
  try:
    # Use our optimized _tail_file here too!
    return _tail_file(path, n)
  except OSError as e:
    logger.error(f"Failed to read last lines of {path}: {e}")
    return []


def _read_chunk(path: Path, offset: int, max_bytes: int = 1024 * 1024) -> tuple[str, int]:
  with path.open("rb") as fh:
    # Check for file truncation/rotation
    try:
      if offset > os.fstat(fh.fileno()).st_size:
        offset = 0
    except OSError:
      offset = 0

    fh.seek(offset)
    chunk_bytes = fh.read(max_bytes)
    new_offset = fh.tell()

    # Decode with error capability (replace or ignore)
    chunk_str = chunk_bytes.decode("utf-8", errors="ignore")

    return chunk_str, new_offset


@app.websocket("/events/stream")
async def events_stream(ws: WebSocket):
  """
  WebSocket-Stream der Event-JSONL-Zeilen.
  Query-Parameter:
    - replay: int   (Anzahl letzter Zeilen zu Beginn; Default 50)
    - heartbeat: int (Sekunden zwischen Heartbeats; Default 15)
  """
  await ws.accept()
  try:
    replay = int(ws.query_params.get("replay", 50))
  except (TypeError, ValueError):
    replay = 50
  try:
    heartbeat_sec = max(3, int(ws.query_params.get("heartbeat", 15)))
  except (TypeError, ValueError):
    heartbeat_sec = 15

  # Initial replay (letzte Zeilen aus der neuesten Datei)
  files = _jsonl_files()
  if files:
    last_file = files[-1]
    for line in _read_last_lines(last_file, replay):
      await ws.send_text(line)
  else:
    last_file = None

  # Tail-Loop (Polling + Rotation)
  # Wir merken uns pro Datei die gelesene Offset-Länge.
  offsets: dict[str, int] = {}
  last_heartbeat = time.time()

  while True:
    try:
      files = _jsonl_files()
      # Sicherstellen, dass wir auch Rotationen mitbekommen
      if not files:
        await asyncio.sleep(1.0)
        # Heartbeat
        if time.time() - last_heartbeat >= heartbeat_sec:
          await ws.send_text(json.dumps({"ts": _timestamp(), "type": "heartbeat"}))
          last_heartbeat = time.time()
        continue

      # Lese neue Zeilen aus der aktuellsten Datei; wenn eine neuere auftaucht, wechsle
      current = files[-1]
      if last_file is None or current != last_file:
        last_file = current
        offsets[str(current)] = 0  # reset offset for new file

      p = current
      p_key = str(p)
      try:
        # Offload blocking I/O to a separate thread
        chunk, new_offset = await asyncio.to_thread(_read_chunk, p, offsets.get(p_key, 0))
        offsets[p_key] = new_offset

        if chunk:
          for line in chunk.splitlines():
            if line.strip():
              await ws.send_text(line)
      except OSError as e:
        # Datei evtl. rotiert oder noch nicht lesbar - ignoriere einmal
        logger.debug(f"Transient error reading {p}: {e}")
        pass

      # Heartbeat senden
      if time.time() - last_heartbeat >= heartbeat_sec:
        await ws.send_text(json.dumps({"ts": _timestamp(), "type": "heartbeat"}))
        last_heartbeat = time.time()

      await asyncio.sleep(1.0)
    except WebSocketDisconnect:
      logger.info("WebSocket disconnected")
      break
    except Exception as exc:  # robust bleiben
      # Fehler ans UI senden, aber Stream nicht abbrechen
      logger.error(f"WebSocket stream error: {exc}")
      try:
        await ws.send_text(json.dumps({"ts": _timestamp(), "type": "error", "detail": str(exc)}))
      except Exception:
        break
