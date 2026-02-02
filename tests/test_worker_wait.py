import shutil
import subprocess
import sys
import time
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure apps module is importable
sys.path.append(os.getcwd())

from apps.worker.run import get_sorted_jobs, wait_for_changes

@pytest.fixture
def queue_dir(tmp_path):
    d = tmp_path / "queue"
    d.mkdir()
    return d

def test_get_sorted_jobs_logic(queue_dir):
    """Verify get_sorted_jobs filters files and sorts correctly."""
    # Mock os.scandir to ensure we control the order/types purely via mock
    with patch("apps.worker.run.os.scandir") as mock_scandir:
        # Setup mock entries
        entry_a = MagicMock()
        entry_a.name = "a.json"
        entry_a.path = str(queue_dir / "a.json")
        entry_a.is_file.return_value = True

        entry_b = MagicMock()
        entry_b.name = "b.json"
        entry_b.path = str(queue_dir / "b.json")
        entry_b.is_file.return_value = True

        entry_c = MagicMock()
        entry_c.name = "c.txt"
        entry_c.path = str(queue_dir / "c.txt")
        entry_c.is_file.return_value = True

        entry_dir = MagicMock()
        entry_dir.name = "dir.json"
        entry_dir.path = str(queue_dir / "dir.json")
        entry_dir.is_file.return_value = False

        # Scandir returns an iterator
        mock_scandir.return_value.__enter__.return_value = [entry_b, entry_c, entry_a, entry_dir]

        jobs = get_sorted_jobs(queue_dir)

        # Check call args
        mock_scandir.assert_called_once_with(queue_dir)

        # Verify is_file called with follow_symlinks=False for the files we cared about
        # We can inspect call_args_list of entry_a
        # It should be called at least once with follow_symlinks=False
        assert entry_a.is_file.call_args.kwargs.get("follow_symlinks") is False
        assert entry_b.is_file.call_args.kwargs.get("follow_symlinks") is False

        # Verify sorting and filtering
        assert len(jobs) == 2
        assert jobs[0].name == "a.json"
        assert jobs[1].name == "b.json"

def test_get_sorted_jobs_typeerror_fallback(queue_dir):
    """Verify fallback to is_file() when follow_symlinks=False raises TypeError."""
    with patch("apps.worker.run.os.scandir") as mock_scandir:
        entry = MagicMock()
        entry.name = "compat.json"
        entry.path = str(queue_dir / "compat.json")

        # side_effect: first call raises TypeError, second call returns True
        entry.is_file.side_effect = [TypeError("unexpected keyword argument"), True]

        mock_scandir.return_value.__enter__.return_value = [entry]

        jobs = get_sorted_jobs(queue_dir)

        assert len(jobs) == 1
        assert jobs[0].name == "compat.json"

        # Check calls:
        # 1. is_file(follow_symlinks=False)
        # 2. is_file()
        assert entry.is_file.call_count == 2

        first_call = entry.is_file.call_args_list[0]
        assert first_call.kwargs.get("follow_symlinks") is False

        second_call = entry.is_file.call_args_list[1]
        assert not second_call.kwargs # Called without args

def test_wait_for_changes_fallback_no_tool(queue_dir):
    """Test fallback to sleep if inotifywait is missing."""
    with patch("shutil.which", return_value=None), \
         patch("time.sleep") as mock_sleep, \
         patch("subprocess.Popen") as mock_popen:

        wait_for_changes(queue_dir)

        mock_sleep.assert_called_once_with(2)
        mock_popen.assert_not_called()

def test_wait_for_changes_success_cleanup(queue_dir):
    """Test standard flow: inotifywait starts, files detected, process cleaned up."""
    with patch("shutil.which", return_value="/usr/bin/inotifywait"), \
         patch("apps.worker.run.get_sorted_jobs") as mock_get_jobs, \
         patch("subprocess.Popen") as mock_popen, \
         patch("apps.worker.run.select.poll") as mock_poll, \
         patch("time.sleep"):  # silence sleep just in case

        # Mock process
        proc = MagicMock()
        proc.stderr.readline.return_value = "Watches established\n"
        proc.poll.return_value = None # Running
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        # Mock select.poll
        poll_instance = MagicMock()
        poll_instance.poll.return_value = True # Ready to read
        mock_poll.return_value = poll_instance

        # Return files directly (simulating files arrived while starting)
        # get_sorted_jobs is called twice:
        # 1. In the check "Double-check if files arrived..."
        # We want it to return files here to trigger the early return path
        mock_get_jobs.return_value = [Path("new.json")]

        wait_for_changes(queue_dir)

        # Verify Popen args include -q
        args, _ = mock_popen.call_args
        cmd = args[0]
        assert "-q" in cmd
        assert "inotifywait" in cmd[0]

        # Verify unregister called
        poll_instance.unregister.assert_called_with(proc.stderr)

        # Verify process cleanup
        proc.terminate.assert_called()

        # Verify streams closed
        proc.stdout.close.assert_called()
        proc.stderr.close.assert_called()

def test_wait_for_changes_process_exit(queue_dir):
    """Test flow where process exits (e.g. event happened)."""
    with patch("shutil.which", return_value=True), \
         patch("apps.worker.run.get_sorted_jobs", return_value=[]), \
         patch("subprocess.Popen") as mock_popen, \
         patch("apps.worker.run.select.poll") as mock_poll:

        proc = MagicMock()
        # Set proc.stderr to None so we skip the confirmation loop entirely
        # ensuring this test focuses purely on the wait/exit logic.
        proc.stderr = None
        # Process is already exited when checked
        proc.poll.return_value = 0
        proc.wait.return_value = 0

        # Explicitly mock stdout to verify close call
        proc.stdout = MagicMock()

        mock_popen.return_value = proc

        poll_instance = MagicMock()
        mock_poll.return_value = poll_instance

        wait_for_changes(queue_dir)

        # Should wait for process (even if poll says 0, wait is called to get exit code)
        proc.wait.assert_called()

        # Process already exited, so terminate should NOT be called
        proc.terminate.assert_not_called()

        # But streams should be closed
        proc.stdout.close.assert_called_once()
        # stderr is None here, so no close on it
