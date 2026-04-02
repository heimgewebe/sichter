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
from lib.findings import Finding

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


def _findings_snapshots_file(path: Path | None = None) -> Path:
    if path is not None:
        return path
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    return INSIGHTS_DIR / "findings.jsonl"


def _serialize_finding(finding: Finding) -> dict[str, object]:
    return {
        "severity": finding.severity,
        "category": finding.category,
        "file": finding.file,
        "line": finding.line,
        "message": finding.message,
        "evidence": finding.evidence,
        "fixAvailable": bool(finding.fix_available),
        "tool": finding.tool,
        "ruleId": finding.rule_id,
        "dedupeKey": finding.dedupe_key,
        "uncertainty": finding.uncertainty,
    }


def _severity_rank(severity: str) -> int:
    order = {
        "critical": 5,
        "error": 4,
        "warning": 3,
        "question": 2,
        "info": 1,
        "ok": 0,
    }
    return order.get(str(severity or "").lower(), -1)


def _top_severity_for_items(items: list[dict[str, object]]) -> str:
    top = "ok"
    best_rank = 0
    for item in items:
        severity = str(item.get("severity") or "ok")
        rank = _severity_rank(severity)
        if rank > best_rank:
            top = severity
            best_rank = rank
    return top


def build_findings_snapshot(
    repo: str,
    findings: list[Finding],
    timestamp: str | None = None,
) -> dict[str, object]:
    """Build an aggregated findings snapshot for a repo."""
    deduped_items: dict[str, dict[str, object]] = {}
    for finding in findings:
        deduped_items[finding.dedupe_key] = _serialize_finding(finding)

    items = sorted(
        deduped_items.values(),
        key=lambda item: (
            -_severity_rank(str(item.get("severity") or "ok")),
            str(item.get("file") or ""),
            int(item.get("line") or 0),
            str(item.get("message") or ""),
        ),
    )

    files: dict[str, list[dict[str, object]]] = {}
    for item in items:
        file_name = str(item.get("file") or "").strip()
        if not file_name:
            continue
        files.setdefault(file_name, []).append(item)

    file_entries = []
    for file_name, file_items in sorted(files.items()):
        file_entries.append(
            {
                "file": file_name,
                "count": len(file_items),
                "topSeverity": _top_severity_for_items(file_items),
            }
        )

    return {
        "repo": repo,
        "ts": timestamp or datetime.now(timezone.utc).isoformat(),
        "count": len(findings),
        "deduped": len(items),
        "files": file_entries,
        "items": items,
    }


def record_findings_snapshot(
    repo: str,
    findings: list[Finding],
    findings_file: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    """Append a detailed findings snapshot for later repo drill-down."""
    snapshot = build_findings_snapshot(repo, findings, timestamp=timestamp)
    target = _findings_snapshots_file(findings_file)
    try:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return snapshot


def load_findings_snapshots(
    n: int = 200,
    findings_file: Path | None = None,
) -> list[dict[str, object]]:
    """Return the last ``n`` findings snapshots."""
    path = _findings_snapshots_file(findings_file)
    if not path.exists():
        return []

    records: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            tail: collections.deque[str] = collections.deque(maxlen=n)
            for line in fh:
                tail.append(line)
        for line in tail:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    except OSError:
        return []
    return records


def latest_findings_snapshot_for_repo(
    repo: str,
    records: list[dict[str, object]],
) -> dict[str, object]:
    """Return the newest persisted findings snapshot for ``repo``."""
    normalized = repo.strip()
    for record in reversed(records):
        if str(record.get("repo") or "").strip() == normalized:
            return record
    return {
        "repo": normalized,
        "ts": None,
        "count": 0,
        "deduped": 0,
        "files": [],
        "items": [],
    }


def summarize_files_for_items(
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build a ``files`` summary from a list of finding items.

    Groups items by file and computes a per-file count and ``topSeverity``.
    The result is sorted alphabetically by file name and mirrors the shape
    used in ``build_findings_snapshot``.

    Args:
        items: Filtered (and optionally sorted) finding item dicts.

    Returns:
        List of ``{"file": str, "count": int, "topSeverity": str}`` dicts.
    """
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in items:
        file_name = str(item.get("file") or "").strip()
        if not file_name:
            continue
        grouped.setdefault(file_name, []).append(item)

    return [
        {
            "file": file_name,
            "count": len(file_items),
            "topSeverity": _top_severity_for_items(file_items),
        }
        for file_name, file_items in sorted(grouped.items())
    ]


def filter_and_sort_items(
    items: list[dict[str, object]],
    *,
    severity: list[str] | None = None,
    category: list[str] | None = None,
    sort: str = "severity",
    sort_dir: str = "desc",
) -> list[dict[str, object]]:
    """Filter and sort finding items.

    Args:
        items: List of finding item dicts.
        severity: If given, only include items whose severity is in this list.
        category: If given, only include items whose category is in this list.
        sort: Field to sort by (``severity``, ``category``, ``file``).
        sort_dir: ``asc`` or ``desc``.

    Returns:
        Filtered and sorted copy of *items*.
    """
    result = list(items)

    if severity:
        allowed = {s.lower() for s in severity}
        result = [i for i in result if str(i.get("severity") or "").lower() in allowed]

    if category:
        allowed = {c.lower() for c in category}
        result = [i for i in result if str(i.get("category") or "").lower() in allowed]

    reverse = sort_dir.lower() != "asc"

    if sort == "category":
        result.sort(
            key=lambda i: (
                str(i.get("category") or ""),
                str(i.get("file") or ""),
                int(i.get("line") or 0),
            ),
            reverse=reverse,
        )
    elif sort == "file":
        result.sort(
            key=lambda i: (
                str(i.get("file") or ""),
                int(i.get("line") or 0),
            ),
            reverse=reverse,
        )
    else:
        # Default: sort by severity.
        # Higher _severity_rank = more severe. desc = most severe first.
        result.sort(
            key=lambda i: (
                _severity_rank(str(i.get("severity") or "ok")),
                str(i.get("file") or ""),
                int(i.get("line") or 0),
                str(i.get("message") or ""),
            ),
            reverse=reverse,
        )

    return result


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


def _top_severity(findings_by_severity: dict[str, int], findings_count: int) -> str:
    """Return the highest-priority severity label for a repo snapshot."""
    for severity in ("critical", "error", "warning", "question", "info"):
        if int(findings_by_severity.get(severity, 0)) > 0:
            return severity
    return "ok" if findings_count <= 0 else "unknown"


def latest_repo_findings(records: list[dict]) -> list[dict]:
    """Return the latest findings snapshot per repo.

    The input is expected to follow the ordering of ``load_metrics()``, i.e. the
    records are processed from oldest to newest so the last record for a repo wins.
    """
    latest: dict[str, dict] = {}

    for record in records:
        repo = str(record.get("repo") or "").strip()
        if not repo:
            continue

        raw_findings = record.get("findings_by_severity") or {}
        findings_by_severity: dict[str, int] = {}
        if isinstance(raw_findings, dict):
            for severity, count in raw_findings.items():
                try:
                    findings_by_severity[str(severity)] = int(count)
                except (TypeError, ValueError):
                    continue

        try:
            findings_count = int(record.get("findings_count", 0))
        except (TypeError, ValueError):
            findings_count = 0

        latest[repo] = {
            "name": repo,
            "findingsCount": max(0, findings_count),
            "findingsBySeverity": findings_by_severity,
            "topSeverity": _top_severity(findings_by_severity, findings_count),
            "lastReviewedAt": record.get("timestamp"),
        }

    return [latest[repo] for repo in sorted(latest)]


def trends_over_time(records: list[dict], days: int = 30) -> list[dict]:
    """Return daily finding counts for the last ``days`` days.

    Missing days are filled with 0 so the caller gets a continuous series.

    Args:
        records: Metric records as returned by :func:`load_metrics`.
        days: Number of calendar days to include.

    Returns:
        List of ``{"date": "YYYY-MM-DD", "findings": int}`` dicts, oldest first.
    """
    from datetime import date, timedelta

    cutoff = date.today() - timedelta(days=days - 1)
    daily: dict[str, int] = {}
    for r in records:
        ts = r.get("timestamp", "")
        if not ts:
            continue
        try:
            day = datetime.fromisoformat(ts).date()
        except (ValueError, TypeError):
            continue
        if day < cutoff:
            continue
        key = day.isoformat()
        daily[key] = daily.get(key, 0) + int(r.get("findings_count", 0))

    result = []
    for offset in range(days):
        d = (cutoff + timedelta(days=offset)).isoformat()
        result.append({"date": d, "findings": daily.get(d, 0)})
    return result


def detect_anomalies(
    records: list[dict],
    window: int = 7,
    threshold_factor: float = 2.5,
) -> list[dict]:
    """Detect repos with a sudden spike in findings relative to their baseline.

    For each repo the function computes a rolling ``window``-day average of
    prior finding counts and flags the repo if the most recent count exceeds
    ``baseline_avg * threshold_factor``.

    Args:
        records: Metric records as returned by :func:`load_metrics`.
        window: Number of days used as the baseline window.
        threshold_factor: Multiplier above which a repo is considered anomalous.

    Returns:
        List of alert dicts with keys:
        ``repo``, ``current_count``, ``baseline_avg``, ``ratio``, ``message``.
    """
    from datetime import date, timedelta

    # Group finding counts by (repo, date)
    repo_daily: dict[str, dict[str, int]] = {}
    all_days: list[str] = []
    for r in records:
        repo = str(r.get("repo") or "").strip()
        ts = r.get("timestamp", "")
        if not repo or not ts:
            continue
        try:
            day = datetime.fromisoformat(ts).date().isoformat()
        except (ValueError, TypeError):
            continue
        repo_daily.setdefault(repo, {})
        repo_daily[repo][day] = repo_daily[repo].get(day, 0) + int(
            r.get("findings_count", 0)
        )
        all_days.append(day)

    if not all_days:
        return []

    # Use the most recent day with any recorded data, not wall-clock today.
    # This avoids false negatives when no run has occurred yet today or when
    # timestamps drift slightly across time zones.
    latest_day = max(all_days)
    baseline_start = (
        datetime.fromisoformat(latest_day).date() - timedelta(days=window)
    ).isoformat()

    alerts: list[dict] = []
    for repo, daily in repo_daily.items():
        current = daily.get(latest_day, 0)
        baseline_vals = [
            v
            for d, v in daily.items()
            if baseline_start <= d < latest_day
        ]
        if not baseline_vals:
            continue
        avg = sum(baseline_vals) / len(baseline_vals)
        if avg <= 0:
            continue
        ratio = current / avg
        if ratio >= threshold_factor:
            alerts.append(
                {
                    "repo": repo,
                    "current_count": current,
                    "baseline_avg": round(avg, 2),
                    "ratio": round(ratio, 2),
                    "message": (
                        f"{repo}: {current} findings on {latest_day} vs avg {avg:.1f} "
                        f"(×{ratio:.1f})"
                    ),
                }
            )
    return sorted(alerts, key=lambda a: a["ratio"], reverse=True)


def review_quality_stats(records: list[dict]) -> dict:
    """Compute review quality statistics from metrics records.

    Derives quality proxies from available data: cache efficiency, PR yield
    (findings → PRs ratio), severity distribution, and LLM token efficiency.

    Args:
        records: Metric records as returned by :func:`load_metrics`.

    Returns:
        Dict with quality stats suitable for the ``/metrics/review-quality`` endpoint.
    """
    if not records:
        return {
            "record_count": 0,
            "cache_hit_rate": 0.0,
            "pr_yield_rate": 0.0,
            "avg_tokens_per_finding": 0.0,
            "findings_by_severity": {},
            "severity_distribution_pct": {},
            "top_repos_by_findings": [],
        }

    total_cache = sum(r.get("cache_hits", 0) for r in records)
    total_tokens = sum(r.get("llm_tokens_used", 0) for r in records)
    total_findings = sum(r.get("findings_count", 0) for r in records)
    total_prs = sum(r.get("prs_created", 0) for r in records)
    total_runs = len(records)

    by_sev: dict[str, int] = {}
    for r in records:
        for sev, cnt in (r.get("findings_by_severity") or {}).items():
            by_sev[sev] = by_sev.get(sev, 0) + int(cnt)

    sev_pct: dict[str, float] = {}
    if total_findings > 0:
        for sev, cnt in by_sev.items():
            sev_pct[sev] = round(cnt / total_findings * 100, 1)

    # Top repos by cumulative finding count
    repo_totals: dict[str, int] = {}
    for r in records:
        repo = str(r.get("repo") or "").strip()
        if repo:
            repo_totals[repo] = repo_totals.get(repo, 0) + int(
                r.get("findings_count", 0)
            )
    top_repos = sorted(repo_totals.items(), key=lambda x: x[1], reverse=True)[:10]

    if total_findings > 0:
        pr_yield_rate = round(total_prs / total_findings, 4)
        avg_tokens_per_finding = round(total_tokens / total_findings, 1)
    else:
        pr_yield_rate = 0.0
        avg_tokens_per_finding = 0.0

    return {
        "record_count": total_runs,
        "cache_hit_rate": round(total_cache / max(total_runs, 1), 2),
        "pr_yield_rate": pr_yield_rate,
        "avg_tokens_per_finding": avg_tokens_per_finding,
        "findings_by_severity": by_sev,
        "severity_distribution_pct": sev_pct,
        "top_repos_by_findings": [
            {"repo": r, "findings": c} for r, c in top_repos
        ],
    }
