"""Review metrics persistence and aggregation."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

INSIGHTS_DIR = Path.home() / ".local" / "state" / "sichter" / "insights"


@dataclass
class ReviewMetrics:
  repo: str
  duration_seconds: float
  findings_count: int
  findings_by_severity: dict[str, int]
  llm_tokens_used: int = 0
  cache_hits: int = 0
  prs_created: int = 0
  timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def record_metrics(metrics: ReviewMetrics, reviews_file: Path | None = None) -> None:
  target = reviews_file
  if target is None:
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    target = INSIGHTS_DIR / "reviews.jsonl"
  try:
    with target.open("a", encoding="utf-8") as handle:
      handle.write(json.dumps(asdict(metrics), ensure_ascii=False) + "\n")
  except OSError:
    return


def load_metrics(n: int = 200, reviews_file: Path | None = None) -> list[dict]:
  target = reviews_file if reviews_file is not None else INSIGHTS_DIR / "reviews.jsonl"
  if not target.exists():
    return []
  try:
    lines = target.read_text(encoding="utf-8").splitlines()
  except OSError:
    return []
  records: list[dict] = []
  for line in lines[-n:]:
    stripped = line.strip()
    if not stripped:
      continue
    try:
      record = json.loads(stripped)
    except json.JSONDecodeError:
      continue
    if isinstance(record, dict):
      records.append(record)
  return records


def aggregate_metrics(records: list[dict]) -> dict:
  if not records:
    return {"count": 0}

  findings_by_severity: dict[str, int] = {}
  for record in records:
    for severity, count in (record.get("findings_by_severity") or {}).items():
      findings_by_severity[severity] = findings_by_severity.get(severity, 0) + int(count)

  total_duration = sum(float(record.get("duration_seconds", 0.0)) for record in records)
  return {
    "count": len(records),
    "total_findings": sum(int(record.get("findings_count", 0)) for record in records),
    "total_prs": sum(int(record.get("prs_created", 0)) for record in records),
    "total_tokens": sum(int(record.get("llm_tokens_used", 0)) for record in records),
    "total_cache_hits": sum(int(record.get("cache_hits", 0)) for record in records),
    "avg_duration_seconds": round(total_duration / len(records), 2),
    "findings_by_severity": findings_by_severity,
    "repos": sorted({str(record.get("repo")) for record in records if record.get("repo")}),
  }
