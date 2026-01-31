import sys
import asyncio
import time
import os
from pathlib import Path
from unittest.mock import MagicMock
from fastapi import Request

# Ensure chronik can be imported
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Mock environment variables BEFORE importing app.main
os.environ["XDG_STATE_HOME"] = str(ROOT / "tmp/xdg_state")
os.environ["REVIEW_ROOT"] = str(ROOT / "tmp/review_root")

from chronik.app.main import job_submit, Settings

# --- Monkeypatching Path.write_text to simulate blocking I/O ---
original_write_text = Path.write_text

def slow_write_text(self, data, encoding=None):
    print("DEBUG: slow_write_text called, sleeping...")
    # Simulate blocking the event loop for 0.5 seconds
    # This happens inside the main thread if the function is not offloaded
    time.sleep(0.5)
    print("DEBUG: slow_write_text finished sleeping.")
    return original_write_text(self, data, encoding=encoding)

Path.write_text = slow_write_text
# ----------------------------------------------------------------

async def heartbeat():
    """
    Checks if the event loop is blocked.
    Ideally, this task should wake up close to every 0.1s.
    """
    print(f"DEBUG: heartbeat starting sleep at {time.time()}")
    start = time.time()
    await asyncio.sleep(0.1)
    end = time.time()
    print(f"DEBUG: heartbeat woke up at {end}")
    diff = end - start
    return diff

async def run_test():
    print("Setting up test environment...")
    settings = Settings()
    # Create necessary directories
    settings.queue_dir.mkdir(parents=True, exist_ok=True)

    # Create a mock request with a JSON payload
    async def mock_json():
        # Yield to allow other tasks (heartbeat) to start
        await asyncio.sleep(0.05)
        return {"test": "payload"}

    req = MagicMock(spec=Request)
    req.json = mock_json

    print("Running job_submit and heartbeat concurrently...")

    # We expect job_submit to block for 0.5s due to slow_write_text.
    # If job_submit blocks the loop, heartbeat (which sleeps 0.1s)
    # won't resume until job_submit finishes (0.5s later).
    # So heartbeat delay will be approx 0.5s instead of 0.1s.

    start_time = time.time()

    task_submit = asyncio.create_task(job_submit(req, settings))
    task_heartbeat = asyncio.create_task(heartbeat())

    await task_submit
    delay = await task_heartbeat

    total_time = time.time() - start_time

    print(f"Total time: {total_time:.4f}s")
    print(f"Heartbeat delay: {delay:.4f}s")

    # If offloaded correctly, heartbeat should wake up around 0.1s (+ small overhead)
    # If blocked, it will be around 0.5s

    if delay > 0.4:
        print("FAIL: Event loop was blocked! (Delay > 0.4s)")
        return False
    else:
        print("PASS: Event loop was responsive. (Delay <= 0.4s)")
        return True

if __name__ == "__main__":
    try:
        success = asyncio.run(run_test())
        if not success:
            sys.exit(1)
    finally:
        # Cleanup monkeypatch
        Path.write_text = original_write_text
