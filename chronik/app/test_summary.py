import os
import sys
from pathlib import Path

# Add the app directory to the Python path
APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT.parent))

# Import module and classes
# We do not need to set os.environ["REVIEW_ROOT"] anymore because we inject it explicitly
from app import main  # noqa: E402
from app.main import Settings

if __name__ == "__main__":
    print(f"Current working directory: {Path.cwd()}")

    # Define test paths explicitly
    test_review_root = Path.cwd() / "sichter" / "review"

    # Instantiate Settings with explicit configuration
    # This avoids reliance on global environment variable side effects for this test
    settings = Settings(review_root=test_review_root)

    print(f"REVIEW_ROOT from settings: {settings.review_root}")
    print(f"INDEX path from settings: {settings.index}")

    # Pass settings explicitly to the function
    result = main.summary(settings=settings)
    print(result)

    assert "total_repos" in result
    print(f"Tests passed (REVIEW_ROOT={settings.review_root})!")
