import os
import sys
from pathlib import Path

# Add the app directory to the Python path
APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT.parent))

# Allow overriding via env, otherwise default to local test path
if "REVIEW_ROOT" not in os.environ:
    os.environ["REVIEW_ROOT"] = str(Path.cwd() / "sichter" / "review")

# IMPORTANT: Import the module *after* setting the env var
from app import main  # noqa: E402

# a little hack to make sure the test uses the correct REVIEW_ROOT and INDEX
# Ensure main module picks up the env var if it wasn't already loaded
main.REVIEW_ROOT = Path(os.environ["REVIEW_ROOT"])
main.INDEX = main.REVIEW_ROOT / "index.json"

print(f"Current working directory: {Path.cwd()}")
print(f"REVIEW_ROOT from env: {os.environ['REVIEW_ROOT']}")
print(f"INDEX path being used: {main.INDEX}")

if __name__ == "__main__":
    result = main.summary()
    print(result)
    # Adjust assertions to be less brittle or dependent on exact test data state if needed
    # but for now keeping them as they verify the test logic
    assert "total_repos" in result
    print(f"Tests passed (REVIEW_ROOT={main.REVIEW_ROOT})!")
