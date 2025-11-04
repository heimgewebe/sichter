import os, sys
from pathlib import Path

# Add the app directory to the Python path
APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT.parent))

# Set the REVIEW_ROOT environment variable to our test data
os.environ["REVIEW_ROOT"] = str(Path.cwd() / "sichter" / "review")

# IMPORTANT: Import the module *after* setting the env var
from app import main

# a little hack to make sure the test uses the correct REVIEW_ROOT and INDEX
main.REVIEW_ROOT = Path(os.environ["REVIEW_ROOT"])
main.INDEX = main.REVIEW_ROOT / "index.json"

print(f"Current working directory: {Path.cwd()}")
print(f"REVIEW_ROOT from env: {os.environ['REVIEW_ROOT']}")
print(f"INDEX path being used: {main.INDEX}")
print(f"Does INDEX exist? {main.INDEX.exists()}")

if __name__ == "__main__":
    result = main.summary()
    print(result)
    assert result["total_repos"] == 3
    assert result["errors"] == 1
    assert result["critical"] == 1
    assert result["warnings"] == 1
    print("Tests passed!")
