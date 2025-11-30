"""Shared configuration and utilities for sichter components."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from lib import simpleyaml

# Centralized path configuration
HOME = Path.home()
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "sichter"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "sichter"
QUEUE = STATE / "queue"
EVENTS = STATE / "events"
LOGS = STATE / "logs"

# Default values
DEFAULT_ORG = "heimgewebe"
DEFAULT_BRANCH = "main"


def ensure_directories() -> None:
    """Ensure all required directories exist."""
    for path in (STATE, CONFIG, QUEUE, EVENTS, LOGS):
        path.mkdir(parents=True, exist_ok=True)


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file using PyYAML if available, fallback to simpleyaml.
    
    Args:
        path: Path to YAML file
        
    Returns:
        Parsed YAML content as dictionary
    """
    if yaml is not None:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    return simpleyaml.load(path)


def get_policy_path() -> Path:
    """Get the path to the active policy file.
    
    Returns:
        Path to policy.yml (user config or repo default)
    """
    user_policy = CONFIG / "policy.yml"
    if user_policy.exists():
        return user_policy
    
    # Fallback to repo default
    # Assuming this is imported from within the repo structure
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "config" / "policy.yml"


def load_policy() -> dict[str, Any]:
    """Load the active policy configuration.
    
    Returns:
        Policy configuration dictionary
    """
    policy_path = get_policy_path()
    if not policy_path.exists():
        return {}
    return load_yaml(policy_path)
