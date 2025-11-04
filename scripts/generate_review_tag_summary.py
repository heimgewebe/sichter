#!/usr/bin/env python3
"""Generate top review tags per repo/month from Hauski parquet insights."""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path


def ensure_duckdb():
    try:
        import duckdb  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "duckdb is required. Install via `pip install --user duckdb`."
        ) from exc


def run(parquet_glob: str, out_path: Path, top_n: int) -> None:
    import duckdb

    matches = glob.glob(parquet_glob)
    if not matches:
        print(f"no parquet files found for pattern: {parquet_glob}", file=sys.stderr)
        return

    con = duckdb.connect()
    query = f"""
        WITH exploded AS (
            SELECT
                repo,
                DATE_TRUNC('month', CAST(ingested_at AS TIMESTAMP)) AS month,
                UNNEST(tags) AS tag,
                score
            FROM read_parquet('{parquet_glob}')
        ),
        stats AS (
            SELECT
                repo,
                strftime(month, '%Y-%m') AS month_label,
                tag,
                COUNT(*) AS tag_count,
                AVG(score) AS avg_score,
                ROW_NUMBER() OVER (
                    PARTITION BY repo, strftime(month, '%Y-%m')
                    ORDER BY COUNT(*) DESC, tag
                ) AS rk
            FROM exploded
            WHERE tag IS NOT NULL
            GROUP BY repo, month, tag
        )
        SELECT
            repo,
            month_label AS month,
            tag,
            tag_count,
            ROUND(avg_score, 2) AS avg_score
        FROM stats
        WHERE rk <= {top_n}
        ORDER BY repo, month, tag_count DESC, tag
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({query}) TO '{out_path}' WITH (HEADER, DELIMITER ',')"
    )
    print(f"wrote summary CSV -> {out_path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet-glob",
        default=str(Path.home() / "sichter" / "insights" / "parquet" / "*.parquet"),
        help="Glob pattern for parquet dataset",
    )
    parser.add_argument(
        "--out",
        default=str(
            Path.home() / "sichter" / "insights" / "reports" / "review_tag_summary.csv"
        ),
        help="Output CSV path",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Top N tags per repo/month",
    )
    args = parser.parse_args(argv)

    ensure_duckdb()
    run(args.parquet_glob, Path(args.out).expanduser(), args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
