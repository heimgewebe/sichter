import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
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
                mock_run_cmd.return_value.stdout = "inside.py\nlink_outside.py\n"
                mock_run_cmd.return_value.returncode = 0

                files = worker_run.get_changed_files(repo_dir)

                # inside.py should be returned
                self.assertIn(repo_dir / "inside.py", files)

                # link_outside.py should NOT be returned because it resolves to outside
                self.assertNotIn(symlink, files)

if __name__ == "__main__":
    unittest.main()
