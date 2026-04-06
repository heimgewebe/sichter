import os
import tempfile
import unittest
from fnmatch import fnmatch
from pathlib import Path
from unittest.mock import patch

from lib.checks.base import compile_excludes, is_excluded, iter_matching_files
from apps.worker.run import iter_paths, get_changed_files

class TestExcludesFunctions(unittest.TestCase):
    def test_compile_excludes_empty(self):
        self.assertIsNone(compile_excludes(()))

    def test_compile_excludes_caching(self):
        self.assertIs(compile_excludes(("*.py",)), compile_excludes(("*.py",)))
        self.assertIsNot(compile_excludes(("*.py",)), compile_excludes(("*.js",)))

    def test_is_excluded_none_or_empty(self):
        self.assertFalse(is_excluded("test.py", None))
        self.assertFalse(is_excluded("test.py", ()))
        self.assertFalse(is_excluded("test.py", []))

    def test_is_excluded_scenarios(self):
        scenarios = [
            ("test.py", ("*.py",), True),
            ("test.py", ("*.js",), False),
            ("test.py", ("*.js", "*.py"), True),
            ("src/foo/bar.py", ("src/*",), True),
            ("src/foo/bar.py", ("src/**/*.py",), True),  # Verify globstar pattern matching parity
            ("src/foo/bar.py", ("*/bar.py",), True),
            ("src/foo/baz.py", ("*/bar.py",), False),
            # Testing Windows-style path vs slashes
            ("src\\\\foo\\\\bar.py", ("src/*",), True) if os.name == "nt" else ("src\\\\foo\\\\bar.py", ("src/*",), False),
            ("SRC/foo/bar.py", ("src/*",), True) if os.name == "nt" else ("SRC/foo/bar.py", ("src/*",), False),
        ]

        for path, excludes, expected in scenarios:
            with self.subTest(path=path, excludes=excludes):
                self.assertEqual(is_excluded(path, excludes), expected)

                # Test equivalence with standard fnmatch list comprehension
                expected_fnmatch = any(fnmatch(path, ex) for ex in excludes)
                self.assertEqual(is_excluded(path, excludes), expected_fnmatch)

    def test_is_excluded_compiled_re(self):
        compiled = compile_excludes(("*.py",))
        self.assertTrue(is_excluded("test.py", compiled))
        self.assertFalse(is_excluded("test.js", compiled))


class TestIterMatchingFiles(unittest.TestCase):
    def test_iter_matching_files_filters_excludes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "test.py").write_text("")
            (repo_dir / "test.js").write_text("")
            (repo_dir / "ignored.py").write_text("")

            files = None  # Simulate all files
            suffixes = {".py", ".js"}
            excludes = ("ignored.py",)

            result = iter_matching_files(repo_dir, files, suffixes, excludes)

            result_names = {p.name for p in result}
            self.assertEqual(result_names, {"test.py", "test.js"})
            self.assertNotIn("ignored.py", result_names)


class TestIterPaths(unittest.TestCase):
    def test_iter_paths_filters_excludes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "test.py").write_text("")
            (repo_dir / "test.js").write_text("")
            (repo_dir / "ignored.py").write_text("")

            result = list(iter_paths(repo_dir, "*", ["ignored.py"]))

            result_names = {p.name for p in result}
            self.assertNotIn("ignored.py", result_names)
            self.assertIn("test.py", result_names)
            self.assertIn("test.js", result_names)


class TestGetChangedFiles(unittest.TestCase):
    def test_get_changed_files_filters_excludes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)

            class MockCompletedProcess:
                def __init__(self, stdout):
                    self.stdout = stdout
                    self.returncode = 0
                    self.stderr = ""

            def mock_run(cmd, *args, **kwargs):
                # Simulate git diff output with an excluded file, a kept file, and an outside relative path
                output = "keep.py\nignored.py\n../outside/path.py\n"
                return MockCompletedProcess(output)

            with patch("apps.worker.run.run_cmd", side_effect=mock_run):
                (repo_dir / "keep.py").write_text("")
                (repo_dir / "ignored.py").write_text("")

                result = get_changed_files(repo_dir, excludes=("ignored.py",))

                result_names = {p.name for p in result}
                self.assertIn("keep.py", result_names)
                self.assertNotIn("ignored.py", result_names)
                self.assertNotIn("path.py", result_names)

if __name__ == "__main__":
    unittest.main()
