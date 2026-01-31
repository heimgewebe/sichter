import asyncio
import time
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi import Request
from chronik.app.main import job_submit, Settings

# Define a slow write function that sleeps
def slow_write_text_mock(self: Path, data: str, encoding=None, errors=None, newline=None):
    time.sleep(0.5) # Simulate blocking I/O
    # Use self (Path) to write
    with open(self, "w", encoding=encoding or "utf-8", errors=errors, newline=newline) as f:
        return f.write(data)

@pytest.mark.asyncio
async def test_job_submit_is_non_blocking(tmp_path, monkeypatch):
    """
    Verifies that job_submit offloads file writing to a thread,
    preventing the event loop from being blocked by slow I/O.
    """
    # Setup settings with tmp_path and ensure queue_dir exists
    settings = Settings(state_root=tmp_path / "state", review_root=tmp_path / "review")
    settings.queue_dir.mkdir(parents=True, exist_ok=True)

    # Mock request
    async def mock_json():
        return {"test": "payload"}
    req = MagicMock(spec=Request)
    req.json = mock_json

    # Monkeypatch Path.write_text to be slow
    monkeypatch.setattr(Path, "write_text", slow_write_text_mock)

    # Define a concurrent heartbeat task
    async def heartbeat():
        start = time.perf_counter()
        await asyncio.sleep(0.1)
        end = time.perf_counter()
        return end - start

    # Run both concurrently
    task_submit = asyncio.create_task(job_submit(req, settings))
    task_heartbeat = asyncio.create_task(heartbeat())

    await task_submit
    delay = await task_heartbeat

    # Check assertions
    # If blocked, delay would be > 0.5s (sleep 0.5 + overhead)
    # If non-blocking, delay should be close to 0.1s (+ overhead)
    # Using 0.45s threshold to be robust against CI load while still catching the 0.5s block
    assert delay < 0.45, f"Event loop was blocked! Delay: {delay:.4f}s"

    # Verify file was actually written and contains correct payload
    files = list(settings.queue_dir.glob("*.json"))
    # We expect at least one file, and we find ours among them
    found_payload = False
    for f in files:
        if f.suffix == ".new":
            continue
        try:
            content = json.loads(f.read_text())
            if content.get("payload") == {"test": "payload"}:
                found_payload = True
                break
        except Exception:
            pass

    assert found_payload, "Job file with expected payload not found in queue"
