import json
import shutil
import time
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Add the app directory to the Python path
APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT.parent))

from app import main
from app.main import Settings

def setup_test_env(root: Path):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    review_root = root / "review"
    review_root.mkdir()

    # Repo 1: report.json exists
    r1 = review_root / "repo1"
    r1.mkdir()
    (r1 / "report.json").write_text('{"severity": "critical"}', encoding="utf-8")
    # Set report.json mtime
    t1 = time.time() - 3600
    os.utime(r1 / "report.json", (t1, t1))

    # Repo 2: fallback to json scan
    r2 = review_root / "repo2"
    r2.mkdir()
    f1 = r2 / "scan_old.json"
    f1.write_text('{"severity": "low"}', encoding="utf-8")
    os.utime(f1, (t1 - 1000, t1 - 1000))

    f2 = r2 / "scan_new.json"
    f2.write_text('{"severity": "high"}', encoding="utf-8")
    t2 = time.time() - 100
    os.utime(f2, (t2, t2))

    # Index
    idx = {"repos": [{"name": "repo1"}, {"name": "repo2"}]}
    (review_root / "index.json").write_text(json.dumps(idx), encoding="utf-8")

    return Settings(review_root=review_root), t1, t2

def test_api_repos():
    test_root = Path("test_temp_api_repos")
    settings, t1, t2 = setup_test_env(test_root)

    try:
        # Mock load_index inside main because it reads from settings
        # actually load_index uses settings, so it works naturally if settings is correct.

        # Call api_repos
        result = main.api_repos(settings=settings)
        items = result["items"]

        assert len(items) == 2

        # Verify Repo 1
        item1 = next(i for i in items if i["name"] == "repo1")
        assert item1["severity"] == "critical"
        # Timestamp should match t1
        ts1_str = item1["updated"]
        # Convert back to float to compare? Or compare strings.
        # Main.py adds "Z" manually: isoformat(timespec="seconds")+"Z"
        expected_ts1 = datetime.fromtimestamp(t1, tz=timezone.utc).isoformat(timespec="seconds")+"Z"
        assert ts1_str == expected_ts1

        # Verify Repo 2
        item2 = next(i for i in items if i["name"] == "repo2")
        assert item2["severity"] == "high" # From scan_new.json
        expected_ts2 = datetime.fromtimestamp(t2, tz=timezone.utc).isoformat(timespec="seconds")+"Z"
        assert item2["updated"] == expected_ts2

        print("test_api_repos PASSED")

    finally:
        shutil.rmtree(test_root)

if __name__ == "__main__":
    test_api_repos()
