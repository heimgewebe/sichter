# apps/api/main.py
import errno
import functools
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
from fastapi import Body, Depends, FastAPI, HTTPException, Security, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from lib.config import CONFIG, EVENTS, QUEUE, ensure_directories, get_policy_path, load_yaml
from .auth import check_api_key

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


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str | None:
  """Verify the API key against the SICHTER_API_KEY environment variable."""
  try:
    check_api_key(api_key, os.environ.get("SICHTER_API_KEY"))
    return api_key
  except ValueError as e:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail=str(e),
    )


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


@app.post(
  "/jobs/submit",
  response_model=JobSubmitResponse,
  responses={500: {"model": ErrorResponse}},
  dependencies=[Depends(verify_api_key)],
)
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


@functools.lru_cache(maxsize=128)
def _read_queue_item_cached(path_str: str, mtime_ns: int, size: int) -> dict:
  try:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as e:
    logger.warning(f"Failed to read/parse queue file {path_str}: {e}")
    return {}


def _cache_bucket(ttl_seconds: float = 2.0) -> int:
  """Return a time bucket for cache invalidation."""
  return int(time.monotonic() // ttl_seconds)


@functools.lru_cache(maxsize=16)
def _scan_files_cached(path_str: str, mtime_ns: int, suffix: str, bucket: int) -> list[tuple[Path, int]]:
  path = Path(path_str)
  entries: list[tuple[Path, int]] = []
  try:
    with os.scandir(path) as it:
      for entry in it:
        if not entry.name.endswith(suffix):
          continue

        try:
          # Robust check: try with follow_symlinks=False (Py3.12+), fallback to default
          try:
            if not entry.is_file(follow_symlinks=False):
              continue
            stat = entry.stat(follow_symlinks=False)
          except TypeError:
            # Fallback for older Python versions
            if not entry.is_file():
              continue
            stat = entry.stat()

          entries.append((Path(entry.path), stat.st_mtime_ns))
        except OSError as e:
          logger.debug("Skipped inaccessible event file %s: %s", entry.path, e)
          continue
  except OSError as e:
    logger.debug("Failed to scan event directory %s: %s", path, e)
    return []

  # Sort by mtime descending (newest first)
  entries.sort(key=lambda x: x[1], reverse=True)
  return entries


def _get_sorted_files(suffix: str) -> list[Path]:
  try:
    stat = EVENTS.stat()
    # dir mtime changes only on add/remove; TTL bucket ensures periodic refresh for append-only workloads.
    bucket = _cache_bucket()
    entries = _scan_files_cached(str(EVENTS), stat.st_mtime_ns, suffix, bucket)
    return [e[0] for e in entries]
  except OSError:
    return []


def _queue_state(limit: int = 10) -> dict[str, int | list[dict]]:
  """Get current queue state with most recent jobs.

  Args:
    limit: Maximum number of queue items to return

  Returns:
    Dictionary with queue size and recent items
  """
  # Collect all queue files first for counting, using scandir for efficiency
  entries: list[tuple[Path, int, int]] = []
  skipped_count = 0
  try:
    with os.scandir(QUEUE) as it:
      for entry in it:
        if not entry.name.endswith(".json"):
          continue

        # Robust check: try with follow_symlinks=False (Py3.12+), fallback to default
        try:
          if not entry.is_file(follow_symlinks=False):
            continue
          stat = entry.stat(follow_symlinks=False)
        except TypeError:
          # Fallback for older Python versions
          if not entry.is_file():
            continue
          stat = entry.stat()
        except OSError:
          skipped_count += 1
          continue

        try:
          entries.append((Path(entry.path), stat.st_mtime_ns, stat.st_size))
        except OSError:
          skipped_count += 1
  except OSError:
    return {"size": 0, "items": []}

  if skipped_count > 0:
    logger.debug(f"Skipped {skipped_count} inaccessible queue files during scandir in {QUEUE}")

  total_size = len(entries)

  # Sort only if needed and get the most recent ones
  if total_size == 0:
    return {"size": 0, "items": []}

  # Sort files by modification time (oldest first) and take last N
  entries.sort(key=lambda x: x[1])
  recent_entries = entries[-limit:] if total_size > limit else entries

  # Build items in chronological order (oldest to newest)
  items: list[dict] = []
  for path, mtime_ns, size in recent_entries:
    # Pass primitives to cache function to ensure stable keys
    payload = _read_queue_item_cached(str(path), mtime_ns, size)
    items.append(
      {
        "id": path.stem,
        "path": str(path),
        "type": payload.get("type"),
        "mode": payload.get("mode"),
        "repo": payload.get("repo"),
        "enqueuedAt": datetime.fromtimestamp(mtime_ns / 1e9, tz=timezone.utc).isoformat(),
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
  files = _get_sorted_files(".jsonl")
  if not files:
    files = _get_sorted_files(".log")

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


@app.get("/events/tail", response_class=PlainTextResponse, dependencies=[Depends(verify_api_key)])
def tail_events(n: int = 200) -> str:
  events = _collect_events(n)
  return "\n".join(entry.get("line", "") for entry in events if entry.get("line"))


@app.get("/events/recent", dependencies=[Depends(verify_api_key)])
def recent_events(n: int = 200) -> dict[str, list]:
  return {"events": _collect_events(n)}


@app.get("/overview", dependencies=[Depends(verify_api_key)])
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


@app.get("/repos/status", dependencies=[Depends(verify_api_key)])
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


@app.post("/settings/policy", dependencies=[Depends(verify_api_key)])
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


@app.get("/settings/policy", dependencies=[Depends(verify_api_key)])
def read_policy() -> dict[str, str]:
  return _read_policy()


# --- websocket: /events/stream ------------------------------------------------


def _jsonl_files() -> list[Path]:
  """Return jsonl event files sorted by mtime ascending."""
  return list(reversed(_get_sorted_files(".jsonl")))


def _read_last_lines(path: Path, n: int) -> list[str]:
  try:
    # Use our optimized _tail_file here too!
    return _tail_file(path, n)
  except OSError as e:
    logger.error(f"Failed to read last lines of {path}: {e}")
    return []


def _read_chunk(path: Path, offset: int, expected_inode: int | None = None, max_bytes: int = 1024 * 1024) -> tuple[str, int, int | None]:
  with path.open("rb") as fh:
    try:
      st = os.fstat(fh.fileno())
      current_inode = st.st_ino
      current_size = st.st_size

      # Check for file rotation (inode change) or truncation
      if (expected_inode is not None and current_inode != expected_inode) or (offset > current_size):
        offset = 0
    except OSError:
      offset = 0
      current_inode = None

    fh.seek(offset)
    chunk_bytes = fh.read(max_bytes)
    new_offset = fh.tell()

    # Decode with error capability (replace or ignore)
    chunk_str = chunk_bytes.decode("utf-8", errors="ignore")

    return chunk_str, new_offset, current_inode


@app.websocket("/events/stream")
async def events_stream(ws: WebSocket, api_key: str | None = Depends(verify_api_key)):
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
  # Wir merken uns pro Datei die gelesene Offset-Länge und Inode.
  offsets: dict[str, int] = {}
  inodes: dict[str, int | None] = {}
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
      p_key = str(current)

      if last_file is None or current != last_file:
        last_file = current

      offsets.setdefault(p_key, 0)
      inodes.setdefault(p_key, None)

      try:
        # Offload blocking I/O to a separate thread
        chunk, new_offset, new_inode = await asyncio.to_thread(
            _read_chunk, current, offsets.get(p_key, 0), inodes.get(p_key)
        )
        offsets[p_key] = new_offset
        inodes[p_key] = new_inode

        if chunk:
          for line in chunk.splitlines():
            if line.strip():
              await ws.send_text(line)
      except OSError as e:
        # Datei evtl. rotiert oder noch nicht lesbar - ignoriere einmal
        logger.debug(f"Transient error reading {current}: {e}")
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
