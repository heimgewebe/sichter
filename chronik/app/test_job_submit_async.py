import time
import json
import threading
from unittest.mock import MagicMock
import pytest
from fastapi import Request
import chronik.app.main
from chronik.app.main import job_submit, Settings

@pytest.mark.asyncio
async def test_job_submit_offloads_write_to_thread(tmp_path, monkeypatch):
    """
    Verifies that job_submit offloads file writing to a thread,
    preventing the event loop from being blocked by slow I/O.
    """
    # Local dictionary to store thread IDs, avoiding global state
    thread_ids = {"main": threading.get_ident(), "write": None}

    # Capture original function to call it within wrapper
    original_write = chronik.app.main.write_job_to_disk

    # Wrapper to introduce delay and capture thread ID
    # Explicit signature ensures we catch API drifts early
    def slow_write_wrapper(queue_dir, jid, data) -> None:
        thread_ids["write"] = threading.get_ident()
        time.sleep(0.5) # Simulate blocking I/O
        original_write(queue_dir, jid, data)

    # Setup settings with tmp_path and ensure queue_dir exists
    settings = Settings(state_root=tmp_path / "state", review_root=tmp_path / "review")
    # write_job_to_disk handles mkdir, but pre-creating is fine to be explicit
    settings.queue_dir.mkdir(parents=True, exist_ok=True)

    # Mock request
    async def mock_json():
        return {"test": "payload"}
    req = MagicMock(spec=Request)
    req.json = mock_json

    # Monkeypatch write_job_to_disk directly to reduce implementation coupling
    monkeypatch.setattr(chronik.app.main, "write_job_to_disk", slow_write_wrapper)

    # Execute the job submission
    await job_submit(req, settings)

    # Check assertions

    # 1. Thread Offloading verification
    assert thread_ids["write"] is not None, "Write function was not called"
    assert thread_ids["write"] != thread_ids["main"], "File write occurred on the main thread!"

    # 3. Verify file was actually written and contains correct payload
    # glob("*.json") excludes .new automatically
    files = list(settings.queue_dir.glob("*.json"))

    found_payload = any(
        json.loads(f.read_text()).get("payload") == {"test": "payload"}
        for f in files
    )
    assert found_payload, "Job file with expected payload not found in queue"
