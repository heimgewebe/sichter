import re
from fnmatch import fnmatch
from pathlib import Path

import pytest

from lib.checks.base import compile_excludes, is_excluded, iter_matching_files
from apps.worker.run import iter_paths, get_changed_files

class TestExcludesFunctions:
    def test_compile_excludes_empty(self):
        assert compile_excludes(()) is None

    def test_compile_excludes_caching(self):
        assert compile_excludes(("*.py",)) is compile_excludes(("*.py",))
        assert compile_excludes(("*.py",)) is not compile_excludes(("*.js",))

    def test_is_excluded_none_or_empty(self):
        assert not is_excluded("test.py", None)
        assert not is_excluded("test.py", ())
        assert not is_excluded("test.py", [])

    @pytest.mark.parametrize(
        "path,excludes,expected",
        [
            ("test.py", ("*.py",), True),
            ("test.py", ("*.js",), False),
            ("test.py", ("*.js", "*.py"), True),
            ("src/foo/bar.py", ("src/*",), True),
            ("src/foo/bar.py", ("src/**/*.py",), True),  # Basic fnmatch doesn't strictly support globstars, but translate does a basic translation. Let's test standard fnmatch equivalence.
            ("src/foo/bar.py", ("*/bar.py",), True),
            ("src/foo/baz.py", ("*/bar.py",), False),
        ]
    )
    def test_is_excluded_scenarios(self, path, excludes, expected):
        assert is_excluded(path, excludes) == expected

        # Test equivalence with standard fnmatch list comprehension
        expected_fnmatch = any(fnmatch(path, ex) for ex in excludes)
        assert is_excluded(path, excludes) == expected_fnmatch

    def test_is_excluded_compiled_re(self):
        compiled = compile_excludes(("*.py",))
        assert is_excluded("test.py", compiled) is True
        assert is_excluded("test.js", compiled) is False

class TestIterMatchingFiles:
    def test_iter_matching_files_filters_excludes(self, tmp_path):
        repo_dir = tmp_path
        (repo_dir / "test.py").write_text("")
        (repo_dir / "test.js").write_text("")
        (repo_dir / "ignored.py").write_text("")

        files = None # Simulate all files
        suffixes = {".py", ".js"}
        excludes = ("ignored.py",)

        result = iter_matching_files(repo_dir, files, suffixes, excludes)

        result_names = {p.name for p in result}
        assert result_names == {"test.py", "test.js"}
        assert "ignored.py" not in result_names

class TestIterPaths:
    def test_iter_paths_filters_excludes(self, tmp_path):
        repo_dir = tmp_path
        (repo_dir / "test.py").write_text("")
        (repo_dir / "test.js").write_text("")
        (repo_dir / "ignored.py").write_text("")

        result = list(iter_paths(repo_dir, "*", ["ignored.py"]))

        result_names = {p.name for p in result}
        assert "ignored.py" not in result_names
        assert "test.py" in result_names
        assert "test.js" in result_names

class TestGetChangedFiles:
    def test_get_changed_files_filters_excludes(self, tmp_path, monkeypatch):
        repo_dir = tmp_path

        # Mock subprocess.run to return predictable git output
        import subprocess
        class MockCompletedProcess:
            def __init__(self, stdout):
                self.stdout = stdout
                self.returncode = 0
                self.stderr = ""

        def mock_run(cmd, *args, **kwargs):
            # Simulated git diff output
            output = "keep.py\nignored.py\noutside/path.py\n"
            return MockCompletedProcess(output)

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Create the files so they exist (get_changed_files might check existence)
        (repo_dir / "keep.py").write_text("")
        (repo_dir / "ignored.py").write_text("")

        # Mock Path.resolve to handle the outside path
        original_resolve = Path.resolve
        def mock_resolve(self, *args, **kwargs):
            if "outside" in str(self):
                return Path("/tmp/outside/path.py")
            return original_resolve(self, *args, **kwargs)
        monkeypatch.setattr(Path, "resolve", mock_resolve)

        result = get_changed_files(repo_dir, excludes=("ignored.py",))

        result_names = {p.name for p in result}
        assert "ignored.py" not in result_names
        assert "keep.py" in result_names
        assert "path.py" not in result_names # Outside path should be skipped
