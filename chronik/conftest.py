import sys
from pathlib import Path

# Ensure the repository root is in sys.path so 'chronik' can be imported as a package
# This matches the behavior needed for running tests from the root or subdirectories
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
