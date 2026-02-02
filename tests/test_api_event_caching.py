
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from apps.api.main import _scan_files_cached, _get_sorted_files, _cache_bucket

class FakeEntry:
    def __init__(self, name, path, is_file=True, mtime_ns=0, raise_on_stat=False):
        self.name = name
        self.path = path
        self._is_file = is_file
        self._mtime_ns = mtime_ns
        self._raise_on_stat = raise_on_stat

    def is_file(self, follow_symlinks=True):
        return self._is_file

    def stat(self, follow_symlinks=True):
        if self._raise_on_stat:
            raise OSError("Inaccessible")

        stat_mock = MagicMock()
        stat_mock.st_mtime_ns = self._mtime_ns
        return stat_mock

@pytest.fixture(autouse=True)
def clear_cache():
    _scan_files_cached.cache_clear()
    yield
    _scan_files_cached.cache_clear()

@pytest.fixture
def mock_scandir():
    with patch("os.scandir") as mock:
        yield mock

def test_scan_files_sorting(mock_scandir):
    entries = [
        FakeEntry("a.jsonl", "/tmp/a.jsonl", mtime_ns=100),
        FakeEntry("b.jsonl", "/tmp/b.jsonl", mtime_ns=300),
        FakeEntry("c.jsonl", "/tmp/c.jsonl", mtime_ns=200),
    ]
    mock_scandir.return_value.__enter__.return_value = entries

    # First call
    result = _scan_files_cached("/tmp", 12345, ".jsonl", bucket=1)

    assert len(result) == 3
    assert result[0][0].name == "b.jsonl" # 300
    assert result[1][0].name == "c.jsonl" # 200
    assert result[2][0].name == "a.jsonl" # 100

def test_scan_files_filtering(mock_scandir):
    entries = [
        FakeEntry("a.jsonl", "/tmp/a.jsonl", mtime_ns=100),
        FakeEntry("b.log", "/tmp/b.log", mtime_ns=300), # Wrong suffix
        FakeEntry("c.jsonl", "/tmp/c.jsonl", is_file=False), # Directory
    ]
    mock_scandir.return_value.__enter__.return_value = entries

    result = _scan_files_cached("/tmp", 12345, ".jsonl", bucket=1)

    assert len(result) == 1
    assert result[0][0].name == "a.jsonl"

def test_scan_files_error_handling(mock_scandir):
    entries = [
        FakeEntry("a.jsonl", "/tmp/a.jsonl", mtime_ns=100),
        FakeEntry("b.jsonl", "/tmp/b.jsonl", raise_on_stat=True), # Error on stat
    ]
    mock_scandir.return_value.__enter__.return_value = entries

    result = _scan_files_cached("/tmp", 12345, ".jsonl", bucket=1)

    assert len(result) == 1
    assert result[0][0].name == "a.jsonl"

def test_cache_invalidation_bucket(mock_scandir):
    entries = [FakeEntry("a.jsonl", "/tmp/a.jsonl", mtime_ns=100)]
    mock_scandir.return_value.__enter__.return_value = entries

    # Call 1
    _scan_files_cached("/tmp", 12345, ".jsonl", bucket=1)
    assert mock_scandir.call_count == 1

    # Call 2 (Same inputs) -> Cache hit
    _scan_files_cached("/tmp", 12345, ".jsonl", bucket=1)
    assert mock_scandir.call_count == 1

    # Call 3 (Different bucket) -> Cache miss
    _scan_files_cached("/tmp", 12345, ".jsonl", bucket=2)
    assert mock_scandir.call_count == 2

@patch("apps.api.main._scan_files_cached")
@patch("apps.api.main._cache_bucket")
@patch("apps.api.main.EVENTS")
def test_get_sorted_files_flow(mock_events, mock_bucket, mock_scan):
    # Setup
    mock_events.stat.return_value.st_mtime_ns = 9999
    mock_events.__str__.return_value = "/events"
    mock_bucket.return_value = 10

    expected_path = Path("/events/a.jsonl")
    mock_scan.return_value = [(expected_path, 100)]

    # Execution
    files = _get_sorted_files(".jsonl")

    # Assertions
    assert len(files) == 1
    assert files[0] == expected_path

    mock_events.stat.assert_called_once()
    mock_bucket.assert_called_once()
    mock_scan.assert_called_once_with(str(mock_events), 9999, ".jsonl", 10)
