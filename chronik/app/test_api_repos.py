import json
import time
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import pytest
from chronik.app import main
from chronik.app.main import Settings

@pytest.fixture
def test_env(tmp_path):
    review_root = tmp_path / "review"
    review_root.mkdir()

    # Repo 1: report.json exists
    r1 = review_root / "repo1"
    r1.mkdir()
    (r1 / "report.json").write_text('{"severity": "critical"}', encoding="utf-8")
    # Set report.json mtime (fixed timestamp to avoid flakiness)
    t1 = 1_700_000_000.0
    os.utime(r1 / "report.json", (t1, t1))

    # Repo 2: fallback to json scan
    r2 = review_root / "repo2"
    r2.mkdir()
    f1 = r2 / "scan_old.json"
    f1.write_text('{"severity": "low"}', encoding="utf-8")
    os.utime(f1, (t1 - 1000, t1 - 1000))

    f2 = r2 / "scan_new.json"
    f2.write_text('{"severity": "high"}', encoding="utf-8")
    t2 = 1_700_000_500.0
    os.utime(f2, (t2, t2))

    # Index
    idx = {"repos": [{"name": "repo1"}, {"name": "repo2"}]}
    (review_root / "index.json").write_text(json.dumps(idx), encoding="utf-8")

    return Settings(review_root=review_root), t1, t2

def test_api_repos(test_env):
    settings, t1, t2 = test_env

    # Call api_repos
    result = main.api_repos(settings=settings)
    items = result["items"]

    assert len(items) == 2

    # Verify Repo 1
    item1 = next(i for i in items if i["name"] == "repo1")
    assert item1["severity"] == "critical"
    # Timestamp should match t1
    ts1_str = item1["updated"]
    expected_ts1 = datetime.fromtimestamp(t1, tz=timezone.utc).isoformat(timespec="seconds")+"Z"
    assert ts1_str == expected_ts1

    # Verify Repo 2
    item2 = next(i for i in items if i["name"] == "repo2")
    assert item2["severity"] == "high" # From scan_new.json
    expected_ts2 = datetime.fromtimestamp(t2, tz=timezone.utc).isoformat(timespec="seconds")+"Z"
    assert item2["updated"] == expected_ts2
