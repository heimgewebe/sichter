import asyncio
import time
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi import Request
from chronik.app.main import job_submit, Settings

# Define a slow write function that sleeps
def slow_write_text_mock(path, data, encoding=None):
    time.sleep(0.5) # Simulate blocking I/O
    # Call the original write_text logic if needed, or just mock it.
    # Since we are mocking the *method* on the Path object, we can't easily call original
    # unless we saved it, but for this test we mainly care about the delay.
    # We will just write to the file to be safe.
    with open(path, "w", encoding=encoding) as f:
        f.write(data)

@pytest.mark.asyncio
async def test_job_submit_is_non_blocking(tmp_path, monkeypatch):
    """
    Verifies that job_submit offloads file writing to a thread,
    preventing the event loop from being blocked by slow I/O.
    """
    # Setup settings with tmp_path
    settings = Settings(state_root=tmp_path / "state", review_root=tmp_path / "review")

    # Mock request
    async def mock_json():
        return {"test": "payload"}
    req = MagicMock(spec=Request)
    req.json = mock_json

    # Monkeypatch Path.write_text to be slow
    # We need to patch it globally for pathlib.Path or specifically where it's used.
    # Since write_job_to_disk uses path_new.write_text(), we patch Path.write_text.

    # Store original to restore? monkeypatch handles restoration.
    monkeypatch.setattr(Path, "write_text", slow_write_text_mock)

    # Define a concurrent heartbeat task
    async def heartbeat():
        start = time.time()
        await asyncio.sleep(0.1)
        end = time.time()
        return end - start

    # Run both concurrently
    task_submit = asyncio.create_task(job_submit(req, settings))
    task_heartbeat = asyncio.create_task(heartbeat())

    await task_submit
    delay = await task_heartbeat

    # Check assertions
    # If blocked, delay would be > 0.5s
    # If non-blocking, delay should be close to 0.1s
    print(f"Heartbeat delay: {delay:.4f}s")
    assert delay < 0.4, f"Event loop was blocked! Delay: {delay:.4f}s"

    # Verify file was actually written (by our mock or logic)
    # The logic in main.py does: write .new, then rename to .json
    # Our mock does the write. The rename happens in main.py (not mocked).
    # Since we mocked write_text, the file should exist at the .new path momentarily,
    # then renamed.
    # Note: write_job_to_disk calls path_new.write_text, then path_new.rename.
    # If we only mock write_text, rename should still work if write_text actually wrote the file.

    # Check if any .json file exists in queue
    files = list(settings.queue_dir.glob("*.json"))
    assert len(files) == 1
    content = json.loads(files[0].read_text())
    assert content["payload"] == {"test": "payload"}
