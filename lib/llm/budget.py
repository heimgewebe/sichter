"""Persistent budget tracking for LLM reviews."""
from __future__ import annotations

import json
import time
from pathlib import Path


class ReviewBudget:
    """Tracks how many LLM reviews were executed in the last hour."""

    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def allow_review(self, max_reviews_per_hour: int, now: float | None = None) -> bool:
        """Return whether another review is permitted under the hourly budget."""
        if max_reviews_per_hour <= 0:
            return False

        entries = self._load_entries()
        current = now if now is not None else time.time()
        window_start = current - 3600
        recent = [e for e in entries if self._ts(e) >= window_start]
        return len(recent) < max_reviews_per_hour

    def reviews_in_last_hour(self, now: float | None = None) -> int:
        """Return count of reviews that were recorded in the current one-hour window."""
        entries = self._load_entries()
        current = now if now is not None else time.time()
        window_start = current - 3600
        return sum(1 for e in entries if self._ts(e) >= window_start)

    @staticmethod
    def _ts(entry: dict) -> float:
        """Return the timestamp from an entry, or 0.0 if missing/invalid."""
        try:
            return float(entry.get("ts", 0.0))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    def record_review(self, repo: str, tokens_used: int, now: float | None = None) -> None:
        """Append one review execution to the budget state file."""
        entry = {
            "ts": now if now is not None else time.time(),
            "repo": repo,
            "tokens_used": max(int(tokens_used), 0),
        }

        try:
            with self.state_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # Budget logging should never break worker execution.
            return

    def _load_entries(self) -> list[dict]:
        if not self.state_file.exists():
            return []

        entries: list[dict] = []
        try:
            with self.state_file.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict):
                        entries.append(data)
        except OSError:
            return []
        return entries
