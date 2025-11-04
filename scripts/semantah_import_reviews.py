#!/usr/bin/env python3
"""Convert Hauski review insights JSONL into parquet files for semantAH dashboards."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL insights into memory."""
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"skipping malformed line: {exc}", file=sys.stderr)
                continue
            if not isinstance(record, dict):
                continue
            records.append(record)
    return records


def build_table(records: list[dict[str, Any]]):
    """Convert dictionaries into a pyarrow.Table."""
    try:
        import pyarrow as pa
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "pyarrow is required. Install via `pip install --user pyarrow`."
        ) from exc

    import pyarrow.parquet as pq  # noqa: F401  # imported for side-effects

    if not records:
        return None

    ingested_at = datetime.now(timezone.utc).isoformat()

    def field(name: str, default: Any = None) -> list[Any]:
        return [record.get(name, default) for record in records]

    tags_array = pa.array(field("tags", []), type=pa.list_(pa.string()))

    table = pa.table(
        {
            "type": field("type", ""),
            "repo": field("repo", ""),
            "source": field("source", ""),
            "file": field("file", ""),
            "pr": field("pr", ""),
            "verdict": field("verdict", ""),
            "score": field("score", 0),
            "tags": tags_array,
            "ingested_at": pa.array([ingested_at] * len(records)),
        }
    )
    return table


def write_parquet(table, out_dir: Path) -> Path:
    """Persist the table to a timestamped parquet file."""
    if table is None or table.num_rows == 0:
        raise SystemExit("no insights found in source JSONL")

    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "pyarrow is required. Install via `pip install --user pyarrow`."
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    out_path = out_dir / f"reviews_{timestamp}.parquet"
    pq.write_table(table, out_path, compression="snappy")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="input_path",
        default=str(Path.home() / ".gewebe" / "insights" / "reviews.jsonl"),
        help="Source JSONL file written by ingest_reviews.py",
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path.home() / ".gewebe" / "insights" / "parquet"),
        help="Target directory for parquet exports",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input_path).expanduser()
    if not input_path.exists():
        print(f"input JSONL not found: {input_path}", file=sys.stderr)
        return 1

    records = read_jsonl(input_path)
    if not records:
        print("no rows exported; nothing to do", file=sys.stderr)
        return 0

    table = build_table(records)
    out_dir = Path(args.out_dir).expanduser()
    out_path = write_parquet(table, out_dir)
    print(f"wrote parquet dataset -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
