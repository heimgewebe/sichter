import os
import sys
from pathlib import Path

# Add the app directory to the Python path
APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT.parent))

# Allow overriding via env, otherwise default to local test path
if "REVIEW_ROOT" not in os.environ:
    os.environ["REVIEW_ROOT"] = str(Path.cwd() / "sichter" / "review")

# Import module and classes
from app import main  # noqa: E402
from app.main import Settings

# Explicitly create settings with the desired configuration
# The Settings class reads os.environ in __init__, so setting it above works.
settings = Settings()

print(f"Current working directory: {Path.cwd()}")
print(f"REVIEW_ROOT from settings: {settings.review_root}")
print(f"INDEX path from settings: {settings.index}")

if __name__ == "__main__":
    # Pass settings explicitly to the function
    result = main.summary(settings=settings)
    print(result)

    assert "total_repos" in result
    print(f"Tests passed (REVIEW_ROOT={settings.review_root})!")
