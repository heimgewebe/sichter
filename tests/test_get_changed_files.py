import unittest
import tempfile
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
from apps.worker import run as worker_run

class TestGetChangedFiles(unittest.TestCase):
    def test_get_changed_files_skips_outside_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            repo_dir = tmp_path / "repo"
            outside_dir = tmp_path / "outside"

            repo_dir.mkdir()
            outside_dir.mkdir()

            # Create a file inside repo
            (repo_dir / "inside.py").touch()

            # Create a file outside repo
            target_file = outside_dir / "target.py"
            target_file.touch()

            # Create symlink in repo pointing outside
            symlink = repo_dir / "link_outside.py"
            try:
                os.symlink(target_file, symlink)
            except OSError:
                self.skipTest("Symlinks not supported")

            # Mock run_cmd to return our file list
            with patch("apps.worker.run.run_cmd") as mock_run_cmd:
                mock_run_cmd.side_effect = [
                    subprocess.CompletedProcess([], 0, stdout="inside.py\nlink_outside.py\n", stderr=""),
                    subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                ]

                files = worker_run.get_changed_files(repo_dir)

                # inside.py should be returned
                self.assertIn(repo_dir / "inside.py", files)

                # link_outside.py should NOT be returned because it resolves to outside
                self.assertNotIn(symlink, files)

    def test_get_changed_files_includes_untracked_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "tracked.py").write_text("print('tracked')\n", encoding="utf-8")
            (repo_dir / "new.py").write_text("print('new')\n", encoding="utf-8")

            with patch("apps.worker.run.run_cmd") as mock_run_cmd:
                mock_run_cmd.side_effect = [
                    subprocess.CompletedProcess([], 0, stdout="tracked.py\n", stderr=""),
                    subprocess.CompletedProcess([], 0, stdout="new.py\n", stderr=""),
                ]

                files = worker_run.get_changed_files(repo_dir)

            self.assertIn(repo_dir / "tracked.py", files)
            self.assertIn(repo_dir / "new.py", files)

if __name__ == "__main__":
    unittest.main()
