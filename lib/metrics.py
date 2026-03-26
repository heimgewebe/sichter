"""Structured metrics collection for sichter reviews.

Each completed repo run emits a ``ReviewMetrics`` record that is appended to
``$XDG_STATE_HOME/sichter/insights/reviews.jsonl``.  The ``/metrics`` API
endpoint aggregates these records on demand.
"""
from __future__ import annotations

import collections
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from lib.config import STATE

INSIGHTS_DIR = STATE / "insights"


@dataclass
class ReviewMetrics:
    """Per-run metrics snapshot."""

    repo: str
    duration_seconds: float
    findings_count: int
    findings_by_severity: dict[str, int]
    llm_tokens_used: int = 0
    cache_hits: int = 0
    prs_created: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def record_metrics(
    metrics: ReviewMetrics,
    reviews_file: Path | None = None,
) -> None:
    """Append a ReviewMetrics record to the insights JSONL file.

    Args:
        metrics: Metrics snapshot to persist.
        reviews_file: Optional override path (for testing).
    """
    if reviews_file is None:
        INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        reviews_file = INSIGHTS_DIR / "reviews.jsonl"
    try:
        with reviews_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(metrics), ensure_ascii=False) + "\n")
    except OSError:
        pass  # non-fatal


def load_metrics(
    n: int = 200,
    reviews_file: Path | None = None,
) -> list[dict]:
    """Return the last ``n`` review metrics records.

    Args:
        n: Maximum number of records to return.
        reviews_file: Optional override path (for testing).

    Returns:
        List of metric dicts, oldest first.
    """
    if reviews_file is None:
        reviews_file = INSIGHTS_DIR / "reviews.jsonl"
    if not reviews_file.exists():
        return []
    records: list[dict] = []
    try:
        with reviews_file.open("r", encoding="utf-8") as fh:
            tail: collections.deque[str] = collections.deque(maxlen=n)
            for line in fh:
                tail.append(line)
        for line in tail:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return records


def aggregate_metrics(records: list[dict]) -> dict:
    """Aggregate a list of metrics records into summary statistics.

    Args:
        records: List of raw metric dicts as returned by :func:`load_metrics`.

    Returns:
        Aggregated summary dict.
    """
    if not records:
        return {
            "count": 0,
            "total_findings": 0,
            "total_prs": 0,
            "total_tokens": 0,
            "total_cache_hits": 0,
            "avg_duration_seconds": 0.0,
            "findings_by_severity": {},
            "repos": [],
        }

    total_findings = sum(r.get("findings_count", 0) for r in records)
    total_prs = sum(r.get("prs_created", 0) for r in records)
    total_tokens = sum(r.get("llm_tokens_used", 0) for r in records)
    total_cache_hits = sum(r.get("cache_hits", 0) for r in records)
    total_duration = sum(r.get("duration_seconds", 0.0) for r in records)

    by_sev: dict[str, int] = {}
    for r in records:
        for sev, count in (r.get("findings_by_severity") or {}).items():
            by_sev[sev] = by_sev.get(sev, 0) + int(count)

    repos = sorted({r.get("repo", "") for r in records if r.get("repo")})

    return {
        "count": len(records),
        "total_findings": total_findings,
        "total_prs": total_prs,
        "total_tokens": total_tokens,
        "total_cache_hits": total_cache_hits,
        "avg_duration_seconds": round(total_duration / len(records), 2),
        "findings_by_severity": by_sev,
        "repos": repos,
    }
